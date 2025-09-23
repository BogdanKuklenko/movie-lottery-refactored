"""Lightweight DHT search utilities."""
from __future__ import annotations

import logging
import time
from typing import List

try:  # pragma: no cover - optional dependency
    import libtorrent as lt  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed when libtorrent is unavailable
    lt = None  # type: ignore[assignment]

_logger = logging.getLogger(__name__)


def _initialise_session() -> "lt.session | None":  # pragma: no cover - thin wrapper
    """Create a libtorrent session configured for in-memory DHT lookups."""

    if lt is None:
        return None

    try:
        session = lt.session()
    except Exception as exc:  # noqa: BLE001 - best-effort initialisation
        _logger.warning("Не удалось инициализировать libtorrent session: %s", exc)
        return None

    try:
        settings = session.get_settings()
    except AttributeError:
        settings = {}

    settings.update(
        {
            "enable_dht": True,
            "enable_upnp": False,
            "enable_natpmp": False,
            "enable_lsd": False,
        }
    )

    try:
        session.apply_settings(settings)
    except Exception:  # noqa: BLE001 - optional call depends on libtorrent version
        for key, value in settings.items():
            try:
                session.set_settings({key: value})
            except Exception:  # noqa: BLE001 - fallback, ignore per-setting errors
                continue

    for host, port in (
        ("router.bittorrent.com", 6881),
        ("router.utorrent.com", 6881),
        ("dht.transmissionbt.com", 6881),
    ):
        try:
            session.add_dht_router(host, port)
        except Exception:  # noqa: BLE001 - routers are optional
            continue

    try:
        session.start_dht()
    except Exception as exc:  # noqa: BLE001 - if DHT fails we fall back to empty result
        _logger.warning("Не удалось запустить DHT: %s", exc)
        try:
            session.abort()
        except Exception:  # noqa: BLE001 - best effort cleanup
            pass
        return None

    return session


def search_via_dht(title: str, timeout: int = 60) -> List[dict]:
    """Perform a best-effort metadata lookup through the DHT network.

    Parameters
    ----------
    title:
        Requested release title.
    timeout:
        Approximate time in seconds spent collecting alerts.

    Returns
    -------
    list[dict]
        Minimal torrent metadata entries. Each dictionary contains the keys
        ``name``, ``info_hash`` and ``seeders``. When the environment lacks a
        DHT implementation the function returns an empty list.
    """

    query = (title or "").strip()
    if not query:
        return []

    session = _initialise_session()
    if session is None:
        return []

    end_time = time.time() + max(1, timeout)
    results: list[dict] = []
    seen_hashes: set[str] = set()

    try:
        while time.time() < end_time:
            try:
                alerts = session.pop_alerts()
            except AttributeError:
                alert = session.pop_alert()
                alerts = [alert] if alert is not None else []

            for alert in alerts:
                alert_type = type(alert).__name__
                if alert_type == "dht_sample_infohashes_alert":
                    for sample in getattr(alert, "samples", []) or []:
                        info_hash = getattr(sample, "to_string", lambda: "")()
                        if not info_hash:
                            continue
                        normalized = info_hash.lower()
                        if normalized in seen_hashes:
                            continue
                        seen_hashes.add(normalized)
                        results.append(
                            {
                                "name": getattr(sample, "name", query),
                                "info_hash": normalized,
                                "seeders": int(getattr(sample, "num_peers", 0) or 0),
                            }
                        )
                elif alert_type == "dht_get_peers_reply_alert":
                    info_hash = getattr(alert, "info_hash", None)
                    if info_hash is None:
                        continue
                    hash_value = getattr(info_hash, "to_string", lambda: "")()
                    if not hash_value:
                        continue
                    normalized = hash_value.lower()
                    if normalized in seen_hashes:
                        continue
                    seen_hashes.add(normalized)
                    results.append(
                        {
                            "name": getattr(alert, "query", query),
                            "info_hash": normalized,
                            "seeders": int(getattr(alert, "num_peers", 0) or 0),
                        }
                    )

            if len(results) >= 25:
                break

            time.sleep(0.1)
    except Exception as exc:  # noqa: BLE001 - network code is inherently fragile
        _logger.debug("Ошибка при работе с DHT: %s", exc)
    finally:
        try:
            session.pause()
        except Exception:  # noqa: BLE001
            pass
        try:
            session.stop_dht()
        except Exception:  # noqa: BLE001
            pass
        try:
            session.abort()
        except Exception:  # noqa: BLE001
            pass

    return results
