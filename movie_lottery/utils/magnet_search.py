"""Utilities for performing background magnet link searches."""
from __future__ import annotations

import logging
import string
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

import requests
from flask import current_app, has_app_context

from .. import db
from ..models import MovieIdentifier
from .magnet_filters import classify_voiceover

DEFAULT_SEARCH_URL = "https://apibay.org/q.php?q={query}"
DEFAULT_TRACKERS = (
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.coppersurfer.tk:6969/announce",
    "udp://tracker.leechers-paradise.org:6969/announce",
    "udp://9.rarbg.to:2710/announce",
    "udp://9.rarbg.me:2710/announce",
)

_logger = logging.getLogger(__name__)

_search_executor = ThreadPoolExecutor(max_workers=3)
_tasks: Dict[int, Dict[str, Any]] = {}
_tasks_lock = Lock()


def _get_configured_value(key: str, default: Any) -> Any:
    if has_app_context():
        return current_app.config.get(key, default)
    return default


def _build_magnet(info_hash: str, name: str, trackers: Optional[Any] = None) -> str:
    trackers = trackers or _get_configured_value("MAGNET_TRACKERS", DEFAULT_TRACKERS)
    if isinstance(trackers, str):
        trackers = [trackers]
    params = [f"xt=urn:btih:{info_hash}", f"dn={quote_plus(name)}"]
    for tracker in trackers or ():
        if tracker:
            params.append(f"tr={quote_plus(str(tracker))}")
    return "magnet:?" + "&".join(params)


def _extract_seeders(payload: Dict[str, Any]) -> int:
    for key in ("seeders", "seeds", "Seeders", "seeders_count", "num_seeders", "seedersCount"):
        if key in payload:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                continue
    return 0


def _extract_info_hash(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("info_hash", "hash", "infoHash", "torrent_hash"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _is_valid_info_hash(value: Optional[str]) -> bool:
    if not value or not isinstance(value, str):
        return False
    normalized = value.strip()
    return len(normalized) == 40 and all(ch in string.hexdigits for ch in normalized)


def search_best_magnet(title: str, *, session: Optional[requests.Session] = None, timeout: int = 15) -> Optional[str]:
    """Searches for the best magnet link matching the provided title.

    The function fetches results from a configurable tracker search endpoint, filters
    them by 1080p quality, and returns the magnet link with the highest number of
    seeders. If nothing suitable is found, ``None`` is returned.
    """

    query = (title or "").strip()
    if not query:
        return None

    session = session or requests.Session()
    base_url = _get_configured_value("MAGNET_SEARCH_URL", DEFAULT_SEARCH_URL)
    try:
        response = session.get(base_url.format(query=quote_plus(query)), timeout=timeout)
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:  # noqa: PERF203 - explicit error message is helpful
            raise RuntimeError("Ответ трекера не в формате JSON") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Ошибка запроса к трекеру: {exc}") from exc

    if isinstance(data, dict) and "results" in data:
        results = data.get("results") or []
    elif isinstance(data, list):
        results = data
    else:
        results = []

    if not results:
        return None

    quality_keywords = ("1080p", "1080")
    filtered: list[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("title") or "")
        lower_name = name.lower()
        if any(q in lower_name for q in quality_keywords):
            filtered.append(item)

    candidates = filtered or [item for item in results if isinstance(item, dict)]
    if not candidates:
        return None

    classified_candidates: list[Dict[str, Any]] = []
    for item in candidates:
        name = str(item.get("name") or item.get("title") or query)
        voice_rank, quality_rank = classify_voiceover(name)
        classified_candidates.append(
            {
                "item": item,
                "name": name,
                "voice_rank": voice_rank,
                "quality_rank": quality_rank,
                "seeders": _extract_seeders(item),
            }
        )

    russian_candidates = [c for c in classified_candidates if c["voice_rank"] >= 0]
    if russian_candidates:
        full_dub = [c for c in russian_candidates if c["voice_rank"] == 0]
        other_russian = [c for c in russian_candidates if c["voice_rank"] > 0]
        sorted_candidates = sorted(
            full_dub,
            key=lambda c: (-c["seeders"], c["quality_rank"]),
        )
        sorted_candidates.extend(
            sorted(
                other_russian,
                key=lambda c: (-c["seeders"], c["quality_rank"]),
            )
        )
        non_russian = [c for c in classified_candidates if c["voice_rank"] < 0]
        sorted_candidates.extend(
            sorted(non_russian, key=lambda c: (-c["seeders"], c["quality_rank"]))
        )
    else:
        sorted_candidates = sorted(
            classified_candidates,
            key=lambda c: (-c["seeders"], c["quality_rank"]),
        )

    trackers = _get_configured_value("MAGNET_TRACKERS", DEFAULT_TRACKERS)
    if isinstance(trackers, str):
        trackers = [trackers]

    for candidate in sorted_candidates:
        item = candidate["item"]
        name = candidate["name"]
        if "no results" in name.lower():
            continue
        magnet = item.get("magnet") or item.get("magnet_link") or item.get("magnetLink")
        if magnet and isinstance(magnet, str) and magnet.strip():
            return magnet
        info_hash = _extract_info_hash(item)
        if not _is_valid_info_hash(info_hash):
            continue
        return _build_magnet(info_hash.strip(), name, trackers)
    return None


def _store_identifier(kinopoisk_id: int, magnet_link: str) -> None:
    identifier = MovieIdentifier.query.get(kinopoisk_id)
    if identifier:
        identifier.magnet_link = magnet_link
    else:
        identifier = MovieIdentifier(kinopoisk_id=kinopoisk_id, magnet_link=magnet_link)
        db.session.add(identifier)


def _search_worker(app, kinopoisk_id: int, query: str) -> Dict[str, Any]:
    with app.app_context():
        result: Dict[str, Any] = {
            "status": "running",
            "kinopoisk_id": kinopoisk_id,
            "query": query,
            "has_magnet": False,
            "magnet_link": "",
        }
        try:
            magnet_link = search_best_magnet(query)
            if magnet_link:
                _store_identifier(kinopoisk_id, magnet_link)
                db.session.commit()
                result.update(
                    {
                        "status": "completed",
                        "has_magnet": True,
                        "magnet_link": magnet_link,
                        "message": "Magnet-ссылка успешно найдена.",
                    }
                )
            else:
                db.session.commit()
                result.update(
                    {
                        "status": "not_found",
                        "message": "Подходящая magnet-ссылка не найдена.",
                    }
                )
        except Exception as exc:  # noqa: BLE001 - логируем и возвращаем ошибку
            db.session.rollback()
            _logger.exception("Ошибка поиска magnet для %s", kinopoisk_id)
            result.update(
                {
                    "status": "failed",
                    "message": f"Ошибка при поиске magnet: {exc}",
                    "error": str(exc),
                }
            )
        return result


def _set_task_entry(kinopoisk_id: int, future: Future, query: str) -> None:
    with _tasks_lock:
        _tasks[kinopoisk_id] = {"future": future, "query": query, "result": None}


def _update_task_result(kinopoisk_id: int, future: Future) -> None:
    try:
        result = future.result()
    except Exception as exc:  # noqa: BLE001 - фиксируем в результатах
        result = {
            "status": "failed",
            "kinopoisk_id": kinopoisk_id,
            "has_magnet": False,
            "magnet_link": "",
            "message": f"Ошибка при поиске magnet: {exc}",
            "error": str(exc),
        }
    with _tasks_lock:
        entry = _tasks.get(kinopoisk_id)
        if entry is not None:
            entry["result"] = result


def _get_task_entry(kinopoisk_id: int) -> Optional[Dict[str, Any]]:
    with _tasks_lock:
        return _tasks.get(kinopoisk_id)


def start_background_search(kinopoisk_id: int, query: str, *, force: bool = False) -> Dict[str, Any]:
    query = (query or "").strip()
    if not query:
        return {
            "status": "failed",
            "kinopoisk_id": kinopoisk_id,
            "has_magnet": False,
            "magnet_link": "",
            "message": "Не указан поисковый запрос.",
        }

    identifier = MovieIdentifier.query.get(kinopoisk_id)
    if identifier and identifier.magnet_link and not force:
        return {
            "status": "completed",
            "kinopoisk_id": kinopoisk_id,
            "has_magnet": True,
            "magnet_link": identifier.magnet_link,
            "message": "Magnet-ссылка уже сохранена.",
        }

    entry = _get_task_entry(kinopoisk_id)
    if entry:
        future = entry.get("future")
        if future and not future.done() and not force:
            return {
                "status": "running",
                "kinopoisk_id": kinopoisk_id,
                "has_magnet": False,
                "magnet_link": "",
                "message": "Поиск уже выполняется.",
            }

    app = current_app._get_current_object()
    future = _search_executor.submit(_search_worker, app, kinopoisk_id, query)
    future.add_done_callback(lambda f, kp_id=kinopoisk_id: _update_task_result(kp_id, f))
    _set_task_entry(kinopoisk_id, future, query)
    return {
        "status": "queued",
        "kinopoisk_id": kinopoisk_id,
        "has_magnet": False,
        "magnet_link": "",
        "message": "Поиск magnet-ссылки запущен.",
    }


def get_search_status(kinopoisk_id: int) -> Dict[str, Any]:
    entry = _get_task_entry(kinopoisk_id)
    if entry:
        future: Future = entry.get("future")
        if future and not future.done():
            return {
                "status": "running",
                "kinopoisk_id": kinopoisk_id,
                "has_magnet": False,
                "magnet_link": "",
                "message": "Поиск выполняется.",
            }
        result = entry.get("result")
        if result is None and future:
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - переводим в понятный ответ
                result = {
                    "status": "failed",
                    "kinopoisk_id": kinopoisk_id,
                    "has_magnet": False,
                    "magnet_link": "",
                    "message": f"Ошибка при поиске magnet: {exc}",
                    "error": str(exc),
                }
            entry["result"] = result
        if result:
            return result

    identifier = MovieIdentifier.query.get(kinopoisk_id)
    if identifier and identifier.magnet_link:
        return {
            "status": "completed",
            "kinopoisk_id": kinopoisk_id,
            "has_magnet": True,
            "magnet_link": identifier.magnet_link,
            "message": "Magnet-ссылка сохранена.",
        }

    return {
        "status": "idle",
        "kinopoisk_id": kinopoisk_id,
        "has_magnet": False,
        "magnet_link": "",
        "message": "Поиск magnet еще не запускался.",
    }
