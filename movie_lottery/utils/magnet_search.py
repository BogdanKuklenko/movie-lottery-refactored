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
from .magnet_scoring import score_quality, score_size, score_voice_category
from .search_preferences import load_search_preferences
from .dht_search import search_via_dht

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


def _extract_size(payload: Dict[str, Any]) -> int:
    try:
        return int(payload.get("size", 0) or 0)
    except (TypeError, ValueError):
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

    candidates = [item for item in results if isinstance(item, dict)]
    if not candidates:
        return None

    def _normalise_http_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
        name = str(item.get("name") or item.get("title") or query)
        magnet_value: Optional[str] = None
        for magnet_key in ("magnet", "magnet_link", "magnetLink"):
            value = item.get(magnet_key)
            if value and isinstance(value, str) and value.strip():
                magnet_value = value.strip()
                break
        return {
            "name": name,
            "seeders": _extract_seeders(item),
            "info_hash": _extract_info_hash(item),
            "magnet": magnet_value,
            "size": _extract_size(item),
        }

    http_candidates = [_normalise_http_candidate(item) for item in candidates]

    def _enrich_candidates(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        enriched: list[Dict[str, Any]] = []
        for payload in items:
            name = str(payload.get("name") or query)
            voice_rank, quality_rank = classify_voiceover(name)
            size = int(payload.get("size") or 0)
            seeders = int(payload.get("seeders") or 0)
            enriched.append(
                {
                    "name": name,
                    "seeders": seeders,
                    "info_hash": payload.get("info_hash"),
                    "magnet": payload.get("magnet"),
                    "size": size,
                    "voice_rank": voice_rank,
                    "quality_rank": quality_rank,
                    "quality_score": score_quality(quality_rank),
                    "voice_score": score_voice_category(voice_rank),
                    "size_score": score_size(size),
                }
            )
        return enriched

    classified_candidates = _enrich_candidates(http_candidates)

    has_russian_1080 = any(
        candidate["voice_rank"] >= 0 and candidate["quality_rank"] == 0
        for candidate in classified_candidates
    )

    fallback_enabled = bool(_get_configured_value("ENABLE_DHT_FALLBACK", False))
    if not has_russian_1080 and fallback_enabled:
        try:
            dht_results = search_via_dht(query)
        except Exception as exc:  # noqa: BLE001 - фиксация ошибок DHT-поиска
            _logger.debug("Ошибка DHT-поиска: %s", exc)
            dht_results = []

        def _normalise_dht_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
            name = str(item.get("name") or query)
            seeders = item.get("seeders")
            try:
                seeders_int = int(seeders)
            except (TypeError, ValueError):
                seeders_int = 0
            return {
                "name": name,
                "seeders": max(seeders_int, 0),
                "info_hash": item.get("info_hash"),
                "magnet": None,
                "size": 0,
            }

        dht_candidates = [
            _normalise_dht_candidate(item)
            for item in dht_results
            if isinstance(item, dict)
        ]
        classified_candidates.extend(_enrich_candidates(dht_candidates))

    if not classified_candidates:
        return None

    preferences = load_search_preferences()
    priority_mapping = {
        "quality": preferences.quality_priority,
        "voice": preferences.voice_priority,
        "size": preferences.size_priority,
    }
    priority_order = sorted(
        [(metric, priority) for metric, priority in priority_mapping.items() if priority],
        key=lambda pair: pair[1],
        reverse=True,
    )

    def _candidate_key(candidate: Dict[str, Any]) -> tuple:
        key_parts: list[Any] = []
        for metric, priority in priority_order:
            if metric == "quality":
                key_parts.append(-priority * candidate["quality_score"])
            elif metric == "voice":
                key_parts.append(-priority * candidate["voice_score"])
            elif metric == "size":
                key_parts.append(-priority * candidate["size_score"])
        key_parts.extend(
            [
                -candidate["seeders"],
                -candidate["voice_score"],
                candidate["quality_rank"],
                candidate["size"],
                candidate["name"].lower(),
            ]
        )
        return tuple(key_parts)

    sorted_candidates = sorted(classified_candidates, key=_candidate_key)

    trackers = _get_configured_value("MAGNET_TRACKERS", DEFAULT_TRACKERS)
    if isinstance(trackers, str):
        trackers = [trackers]

    for candidate in sorted_candidates:
        name = candidate["name"]
        if "no results" in name.lower():
            continue
        magnet = candidate.get("magnet")
        if magnet and isinstance(magnet, str) and magnet.strip():
            return magnet
        info_hash = candidate.get("info_hash")
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
