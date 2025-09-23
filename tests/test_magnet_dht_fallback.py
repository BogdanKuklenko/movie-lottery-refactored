"""Tests validating DHT fallback behaviour for magnet search."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from contextlib import contextmanager

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


movie_lottery_pkg = sys.modules.setdefault("movie_lottery", types.ModuleType("movie_lottery"))
movie_lottery_pkg.__path__ = [str(PROJECT_ROOT / "movie_lottery")]
movie_lottery_pkg.db = types.SimpleNamespace(
    session=types.SimpleNamespace(
        add=lambda *args, **kwargs: None,
        commit=lambda *args, **kwargs: None,
        rollback=lambda *args, **kwargs: None,
    )
)


utils_pkg = sys.modules.setdefault("movie_lottery.utils", types.ModuleType("movie_lottery.utils"))
utils_pkg.__path__ = [str(PROJECT_ROOT / "movie_lottery" / "utils")]


class _Query:
    def get(self, *_args, **_kwargs):
        return None


class _MovieIdentifier:
    query = _Query()


class _SearchPreference:
    query = _Query()

    def __init__(self, id=1):  # noqa: D401 - simple stub
        self.id = id
        self.quality_priority = 0
        self.voice_priority = 0
        self.size_priority = 0


models_module = sys.modules.setdefault("movie_lottery.models", types.ModuleType("movie_lottery.models"))
models_module.MovieIdentifier = _MovieIdentifier
models_module.SearchPreference = _SearchPreference


MAGNET_SEARCH_PATH = PROJECT_ROOT / "movie_lottery" / "utils" / "magnet_search.py"
spec = importlib.util.spec_from_file_location(
    "movie_lottery.utils.magnet_search",
    MAGNET_SEARCH_PATH,
)
assert spec and spec.loader is not None
magnet_search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = magnet_search
spec.loader.exec_module(magnet_search)


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - no-op
        return None

    def json(self):
        return self._payload


class _DummySession:
    def __init__(self, payload):
        self._payload = payload

    def get(self, url, timeout):  # pragma: no cover - signature compatibility
        return _DummyResponse(self._payload)


class _AppStub:
    @contextmanager
    def app_context(self):
        yield self


def test_dht_fallback_returns_magnet_and_stores_final_link(monkeypatch):
    http_payload = {
        "results": [
            {
                "name": "Фильм 2024 WEBRip 720p без перевода",
                "magnet": "",
                "info_hash": "123",
                "seeders": 42,
                "size": 1_500,
            }
        ]
    }
    dht_name = "Фильм 2024 WEB-DL 1080p профессиональный дубляж"
    dht_info_hash = "A" * 40
    dht_payload = [
        {
            "name": dht_name,
            "info_hash": dht_info_hash,
            "seeders": 320,
        }
    ]

    monkeypatch.setattr(magnet_search.requests, "Session", lambda: _DummySession(http_payload))
    monkeypatch.setattr(magnet_search, "search_via_dht", lambda _query: dht_payload)
    monkeypatch.setattr(magnet_search, "has_app_context", lambda: False)

    def _fake_get_configured_value(key, default):
        if key == "ENABLE_DHT_FALLBACK":
            return True
        return default

    monkeypatch.setattr(magnet_search, "_get_configured_value", _fake_get_configured_value)

    expected_magnet = magnet_search._build_magnet(
        dht_info_hash,
        dht_name,
        magnet_search.DEFAULT_TRACKERS,
    )

    magnet_link = magnet_search.search_best_magnet("Фильм 2024")
    assert magnet_link == expected_magnet

    store_calls: list[tuple[int, str]] = []
    monkeypatch.setattr(
        magnet_search,
        "_store_identifier",
        lambda kinopoisk_id, magnet: store_calls.append((kinopoisk_id, magnet)),
    )

    worker_result = magnet_search._search_worker(_AppStub(), 512, "Фильм 2024")

    assert store_calls == [(512, expected_magnet)]
    assert worker_result["status"] == "completed"
    assert worker_result["has_magnet"] is True
    assert worker_result["magnet_link"] == expected_magnet


def test_search_via_dht_collects_metadata(monkeypatch):
    from movie_lottery.utils import dht_search

    sample_hash = "0123456789ABCDEF0123456789ABCDEF01234567"
    release_name = "Example Movie 2024 WEB-DL 1080p"
    seeder_count = 128

    class _Sha1Hash:
        def __init__(self, data):
            self._data = bytes(data)

        def to_bytes(self):
            return self._data

    class _SettingsPack:
        enable_lsd = 1
        enable_upnp = 2
        enable_natpmp = 3
        enable_dht = 4
        alert_mask = 5
        listen_interfaces = 6

        def __init__(self):
            self.values = {}

        def set_bool(self, name, value):  # pragma: no cover - simple stub
            self.values[name] = value

        def set_int(self, name, value):  # pragma: no cover - simple stub
            self.values[name] = value

        def set_str(self, name, value):  # pragma: no cover - simple stub
            self.values[name] = value

    class _AlertCategory:
        dht_notification = 1

    class _Alert:
        category_t = _AlertCategory()

    class dht_sample_infohashes_alert:  # noqa: N801 - mimic libtorrent class name
        def __init__(self, samples):
            self.samples = samples

        def category(self):  # pragma: no cover - compatibility
            return 1

    class metadata_received_alert:  # noqa: N801 - mimic libtorrent class name
        def __init__(self, handle):
            self.handle = handle

    class _TorrentInfo:
        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

    class _TorrentStatus:
        def __init__(self, name, seeds):
            self.name = name
            self.num_seeds = seeds

    class _Handle:
        def __init__(self, info_hash, name, seeds):
            self._hash = info_hash
            self._info = _TorrentInfo(name)
            self._status = _TorrentStatus(name, seeds)

        def info_hash(self):
            return self._hash

        def get_torrent_info(self):
            return self._info

        def status(self):
            return self._status

    class _AddTorrentParams:
        def __init__(self):
            self.info_hash = None
            self.flags = 0
            self.save_path = ""

    class _Session:
        instances = []

        def __init__(self, _settings):
            self._alerts = []
            self.removed = []
            self.added = []
            _Session.instances.append(self)

        def add_dht_router(self, *_args, **_kwargs):  # pragma: no cover - no-op
            return None

        def start_dht(self):  # pragma: no cover - no-op
            return None

        def pause(self):  # pragma: no cover - mark paused
            self.paused = True

        def dht_sample_infohashes(self, _target):
            sha1 = _Sha1Hash(bytes.fromhex(sample_hash))
            self._alerts.append(dht_sample_infohashes_alert([sha1]))

        def wait_for_alert(self, _timeout):
            return self._alerts[0] if self._alerts else None

        def pop_alerts(self):
            alerts, self._alerts = self._alerts, []
            return alerts

        def add_torrent(self, params):
            info_hash = params.info_hash
            self.added.append(info_hash.to_bytes().hex())
            handle = _Handle(info_hash, release_name, seeder_count)
            self._alerts.append(metadata_received_alert(handle))
            return handle

        def remove_torrent(self, handle, *_args):
            self.removed.append(handle.info_hash().to_bytes().hex())

    class _TorrentFlags:
        upload_mode = 1 << 0
        stop_when_ready = 1 << 1
        auto_managed = 1 << 2
        duplicate_is_error = 1 << 3
        need_save_resume = 1 << 4

    class _Options:
        delete_files = 1

    class _StubLibtorrent:
        settings_pack = _SettingsPack
        alert = _Alert
        torrent_flags = _TorrentFlags
        options_t = _Options
        session = _Session

        @staticmethod
        def add_torrent_params():
            return _AddTorrentParams()

        @staticmethod
        def sha1_hash(data):
            return _Sha1Hash(data)

    monkeypatch.setattr(dht_search, "lt", _StubLibtorrent())

    results = dht_search.search_via_dht("Example Movie")

    assert results == [
        {"name": release_name, "info_hash": sample_hash.lower(), "seeders": seeder_count}
    ]

    session = _Session.instances[0]
    assert session.added == [sample_hash.lower()]
    assert session.removed == [sample_hash.lower()]
