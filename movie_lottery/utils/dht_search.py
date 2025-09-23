"""DHT-based torrent lookup helpers."""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Set, Tuple

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

_MAX_METADATA_REQUESTS = 20


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


def _hexlify_sha1(hash_value: "lt.sha1_hash") -> str:
    try:
        raw = hash_value.to_bytes()
    except AttributeError:  # pragma: no cover - older libtorrent versions
        raw = hash_value.to_string()  # type: ignore[attr-defined]
    return raw.hex()


def _ensure_sha1_hash(value: object) -> Optional[Tuple["lt.sha1_hash", str]]:
    """Normalise an arbitrary value into ``lt.sha1_hash`` and its hex digest."""

    if value is None:
        return None
    try:
        if hasattr(value, "to_bytes") or hasattr(value, "to_string"):
            hash_obj = value  # type: ignore[assignment]
        elif isinstance(value, (bytes, bytearray)):
            hash_obj = lt.sha1_hash(bytes(value))
        elif isinstance(value, str):
            if len(value.strip()) != 40:
                return None
            hash_obj = lt.sha1_hash(bytes.fromhex(value.strip()))
        else:
            return None
        digest = _hexlify_sha1(hash_obj)
    except Exception:  # pragma: no cover - best effort normalisation
        return None
    return hash_obj, digest


def _create_add_torrent_params(info_hash: "lt.sha1_hash") -> Optional["lt.add_torrent_params"]:
    """Create ``add_torrent_params`` configured for metadata-only downloads."""

    if not hasattr(lt, "add_torrent_params"):
        return None
    try:
        params = lt.add_torrent_params()
    except Exception:  # pragma: no cover - construction failure
        return None

    try:
        params.info_hash = info_hash  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - fallback assignment
        setattr(params, "info_hash", info_hash)

    flags = getattr(params, "flags", 0)
    for flag_name in ("upload_mode", "stop_when_ready", "auto_managed", "duplicate_is_error"):
        flag_value = getattr(getattr(lt, "torrent_flags", object()), flag_name, None)
        if flag_value is not None:
            flags |= flag_value
    need_save_resume = getattr(getattr(lt, "torrent_flags", object()), "need_save_resume", None)
    if need_save_resume is not None:
        flags &= ~need_save_resume
    params.flags = flags

    if not getattr(params, "save_path", None):
        params.save_path = "."

    return params


def _remove_torrent_handle(session: "lt.session", handle: "lt.torrent_handle") -> None:
    """Safely remove a torrent handle from the session."""

    try:
        delete_flag = getattr(getattr(lt, "options_t", object()), "delete_files", None)
        if delete_flag is not None:
            session.remove_torrent(handle, delete_flag)
        else:
            session.remove_torrent(handle)
    except Exception:  # pragma: no cover - best effort cleanup
        pass


def _extract_torrent_name(handle: "lt.torrent_handle") -> Optional[str]:
    """Extract torrent name from a metadata-ready handle."""

    candidates: List[str] = []
    try:
        info = handle.get_torrent_info()
    except Exception:
        info = None
    if info is not None:
        try:
            name = info.name()
            if name:
                candidates.append(str(name))
        except Exception:
            pass

    try:
        status = handle.status()
    except Exception:
        status = None
    if status is not None:
        for attr in ("name", "torrent_name"):
            value = getattr(status, attr, None)
            if value:
                candidates.append(str(value))

    for value in candidates:
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


def _extract_torrent_seeders(handle: "lt.torrent_handle") -> int:
    """Extract seeder count from torrent handle status."""

    try:
        status = handle.status()
    except Exception:
        return 0
    for attr in ("num_seeds", "num_seeders", "num_complete", "list_seeds"):
        value = getattr(status, attr, None)
        if value is None:
            continue
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            continue
    return 0


def search_via_dht(title: str, timeout: int = 60) -> List[Dict[str, object]]:
    """Perform a temporary DHT lookup and fetch torrent metadata for ``title``."""

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
    requested: Set[str] = set()
    pending_handles: Dict[str, "lt.torrent_handle"] = {}

    try:
        try:
            try:
                target = lt.sha1_hash(b"\x00" * 20)
            except Exception as exc:
                _logger.error("libtorrent не поддерживает sha1_hash: %s", exc)
                session.pause()
                return []
            # Request a random sample of info hashes from the DHT network.
            session.dht_sample_infohashes(target)
        except Exception as exc:
            _logger.error("Ошибка при запуске DHT поиска: %s", exc)
            session.pause()
            return []

        deadline = time.time() + max(1, int(timeout or 0))
        while time.time() < deadline:
            if results and not pending_handles:
                break
            try:
                session.wait_for_alert(1.0)
            except Exception as exc:
                _logger.debug("Ошибка ожидания алертов DHT: %s", exc)
                break
            for event in session.pop_alerts():
                if event is None:
                    continue
                event_name = event.__class__.__name__

                if event_name == "dht_sample_infohashes_alert":
                    samples = getattr(event, "samples", []) or []
                    for sample in samples:
                        if len(requested) >= _MAX_METADATA_REQUESTS:
                            break
                        normalized = _ensure_sha1_hash(sample)
                        if not normalized:
                            continue
                        info_hash, hash_hex = normalized
                        if hash_hex in requested:
                            continue
                        params = _create_add_torrent_params(info_hash)
                        if params is None:
                            _logger.debug("libtorrent не поддерживает временные запросы метаданных")
                            return []
                        try:
                            handle = session.add_torrent(params)
                        except Exception as exc:
                            _logger.debug("Не удалось добавить торрент %s: %s", hash_hex, exc)
                            continue
                        requested.add(hash_hex)
                        pending_handles[hash_hex] = handle
                elif event_name == "metadata_received_alert":
                    handle = getattr(event, "handle", None)
                    if handle is None:
                        continue
                    try:
                        info_hash = handle.info_hash()
                    except Exception:
                        info_hash = None
                    normalized = _ensure_sha1_hash(info_hash)
                    if not normalized:
                        _remove_torrent_handle(session, handle)
                        continue
                    _, hash_hex = normalized
                    name = _extract_torrent_name(handle)
                    if not name:
                        _remove_torrent_handle(session, handle)
                        pending_handles.pop(hash_hex, None)
                        continue
                    seeders = _extract_torrent_seeders(handle)
                    results[hash_hex] = {"name": name, "info_hash": hash_hex, "seeders": seeders}
                    _remove_torrent_handle(session, handle)
                    pending_handles.pop(hash_hex, None)
                elif event_name in {"torrent_removed_alert", "torrent_deleted_alert"}:
                    handle = getattr(event, "handle", None)
                    try:
                        info_hash = handle.info_hash() if handle else None
                    except Exception:
                        info_hash = None
                    normalized = _ensure_sha1_hash(info_hash) if info_hash else None
                    if normalized:
                        _, hash_hex = normalized
                        pending_handles.pop(hash_hex, None)
                elif event_name in {"torrent_error_alert", "metadata_failed_alert"}:
                    handle = getattr(event, "handle", None)
                    if handle is None:
                        continue
                    try:
                        info_hash = handle.info_hash()
                    except Exception:
                        info_hash = None
                    normalized = _ensure_sha1_hash(info_hash) if info_hash else None
                    if normalized:
                        _, hash_hex = normalized
                        pending_handles.pop(hash_hex, None)
                    _remove_torrent_handle(session, handle)
    finally:
        try:
            for handle in pending_handles.values():
                _remove_torrent_handle(session, handle)
        finally:
            try:
                session.pause()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    # Ensure the output only contains valid info hashes and names.
    return [item for item in results.values() if item.get("name") and item.get("info_hash")]
