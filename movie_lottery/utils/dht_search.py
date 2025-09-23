"""DHT-based torrent lookup helpers."""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, List

_logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency handling
    import libtorrent as lt  # type: ignore
except Exception:  # pragma: no cover - libtorrent is optional
    lt = None  # type: ignore
    _logger.debug("`libtorrent` is not installed; DHT search will be disabled.")


_DHT_ROUTERS = (
    ("router.bittorrent.com", 6881),
    ("router.utorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
)


def _apply_setting(settings: "lt.settings_pack", name: int, value: object) -> None:
    """Apply a setting value to a ``libtorrent.settings_pack`` instance."""

    try:
        if isinstance(value, bool):
            settings.set_bool(name, value)
        elif isinstance(value, str):
            settings.set_str(name, value)
        elif isinstance(value, int):
            settings.set_int(name, value)
    except AttributeError:  # pragma: no cover - compatibility with older libtorrent
        setattr(settings, name, value)


def _create_ephemeral_session() -> "lt.session":
    """Create a temporary libtorrent session configured for DHT lookups."""

    settings = lt.settings_pack()
    _apply_setting(settings, lt.settings_pack.enable_lsd, False)
    _apply_setting(settings, lt.settings_pack.enable_upnp, False)
    _apply_setting(settings, lt.settings_pack.enable_natpmp, False)
    _apply_setting(settings, lt.settings_pack.enable_dht, True)
    _apply_setting(settings, lt.settings_pack.alert_mask, lt.alert.category_t.dht_notification)
    _apply_setting(settings, lt.settings_pack.listen_interfaces, "0.0.0.0:0")

    session = lt.session(settings)
    for host, port in _DHT_ROUTERS:
        try:
            session.add_dht_router(host, port)
        except Exception:  # pragma: no cover - ignore router errors
            continue
    try:
        session.start_dht()
    except Exception as exc:  # pragma: no cover - surface error to caller
        session.pause()
        raise RuntimeError("Не удалось запустить DHT-сессию") from exc
    return session


def _to_sha1_hash(query: str) -> "lt.sha1_hash":
    digest = hashlib.sha1(query.encode("utf-8", "ignore")).digest()
    return lt.sha1_hash(digest)


def _hexlify_sha1(hash_value: "lt.sha1_hash") -> str:
    try:
        raw = hash_value.to_bytes()
    except AttributeError:  # pragma: no cover - older libtorrent versions
        raw = hash_value.to_string()  # type: ignore[attr-defined]
    return raw.hex()


def search_via_dht(title: str, timeout: int = 60) -> List[Dict[str, object]]:
    """Perform an in-memory DHT lookup for torrents related to ``title``.

    The function spawns an ephemeral libtorrent session, performs a DHT lookup
    using ``dht_get_peers`` and collects reply alerts within the provided
    timeout. The resulting dictionaries contain ``name``, ``info_hash`` and
    ``seeders`` fields. In case ``libtorrent`` is not available or an error
    occurs during the lookup, an empty list is returned.
    """

    query = (title or "").strip()
    if not query:
        return []

    if lt is None:  # pragma: no cover - optional dependency
        _logger.warning("DHT поиск недоступен: библиотека libtorrent не установлена.")
        return []

    try:
        session = _create_ephemeral_session()
    except Exception as exc:
        _logger.error("Не удалось инициализировать DHT поиск: %s", exc)
        return []

    results: Dict[str, Dict[str, object]] = {}
    target_hash = _to_sha1_hash(query)

    try:
        session.dht_get_peers(target_hash)
    except Exception as exc:
        _logger.error("Ошибка при запуске DHT поиска: %s", exc)
        session.pause()
        return []

    deadline = time.time() + max(1, int(timeout or 0))
    try:
        while time.time() < deadline:
            try:
                alert = session.wait_for_alert(1.0)
            except Exception as exc:
                _logger.debug("Ошибка ожидания алертов DHT: %s", exc)
                break
            if not alert:
                continue
            for event in session.pop_alerts():
                if event is None:
                    continue
                if event.category() & lt.alert.category_t.dht_notification == 0:
                    continue
                if event.__class__.__name__ == "dht_get_peers_reply_alert":
                    info_hash = getattr(event, "info_hash", None)
                    peers = getattr(event, "peers", []) or []
                    if not info_hash:
                        continue
                    try:
                        hash_hex = _hexlify_sha1(info_hash)
                    except Exception:
                        continue
                    item = results.setdefault(
                        hash_hex,
                        {"name": query, "info_hash": hash_hex, "seeders": 0},
                    )
                    try:
                        item["seeders"] = max(item["seeders"], len(peers))
                    except TypeError:
                        item["seeders"] = len(peers)
                elif event.__class__.__name__ == "dht_announce_alert":
                    info_hash = getattr(event, "info_hash", None)
                    if not info_hash:
                        continue
                    try:
                        hash_hex = _hexlify_sha1(info_hash)
                    except Exception:
                        continue
                    item = results.setdefault(
                        hash_hex,
                        {"name": query, "info_hash": hash_hex, "seeders": 0},
                    )
                    item["seeders"] = max(int(item.get("seeders", 0)), 1)
    finally:
        try:
            session.pause()
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    return list(results.values())
