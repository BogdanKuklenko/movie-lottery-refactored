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
