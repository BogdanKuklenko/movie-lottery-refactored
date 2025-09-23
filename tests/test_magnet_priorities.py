"""Tests covering magnet search prioritisation logic."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from dataclasses import dataclass

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]

movie_lottery_pkg = types.ModuleType("movie_lottery")
movie_lottery_pkg.__path__ = [str(PROJECT_ROOT / "movie_lottery")]
movie_lottery_pkg.db = types.SimpleNamespace(
    session=types.SimpleNamespace(add=lambda *args, **kwargs: None, commit=lambda: None, rollback=lambda: None)
)
sys.modules.setdefault("movie_lottery", movie_lottery_pkg)

utils_pkg = types.ModuleType("movie_lottery.utils")
utils_pkg.__path__ = [str(PROJECT_ROOT / "movie_lottery" / "utils")]
sys.modules.setdefault("movie_lottery.utils", utils_pkg)


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


models_module = types.ModuleType("movie_lottery.models")
models_module.MovieIdentifier = _MovieIdentifier
models_module.SearchPreference = _SearchPreference
sys.modules.setdefault("movie_lottery.models", models_module)

MAGNET_SEARCH_PATH = PROJECT_ROOT / "movie_lottery" / "utils" / "magnet_search.py"
spec = importlib.util.spec_from_file_location(
    "movie_lottery.utils.magnet_search",
    MAGNET_SEARCH_PATH,
)
assert spec and spec.loader is not None
magnet_search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = magnet_search
spec.loader.exec_module(magnet_search)


@dataclass
class SearchPriorities:
    quality_priority: int = 0
    voice_priority: int = 0
    size_priority: int = 0
    auto_search_enabled: bool = True


FAKE_RESULTS = [
    {
        "name": "Фильм 4K полный дубляж",
        "magnet": "magnet_voice_priority",
        "seeders": 70,
        "size": 2500,
    },
    {
        "name": "Фильм 1080p многоголос",
        "magnet": "magnet_quality_priority",
        "seeders": 120,
        "size": 2800,
    },
    {
        "name": "Фильм 720p профессиональный дубляж компактный релиз",
        "magnet": "magnet_size_priority",
        "seeders": 90,
        "size": 1400,
    },
    {
        "name": "Фильм 1080p без перевода",
        "magnet": "magnet_without_voice",
        "seeders": 600,
        "size": 2600,
    },
]


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


@pytest.fixture(autouse=True)
def _stub_tracker_session(monkeypatch):
    monkeypatch.setattr(
        magnet_search.requests,
        "Session",
        lambda: _DummySession(FAKE_RESULTS),
    )


@pytest.mark.parametrize(
    ("priorities", "expected_magnet"),
    [
        (
            SearchPriorities(quality_priority=5, voice_priority=1, size_priority=0),
            "magnet_quality_priority",
        ),
        (
            SearchPriorities(quality_priority=1, voice_priority=5, size_priority=0),
            "magnet_voice_priority",
        ),
        (
            SearchPriorities(quality_priority=0, voice_priority=0, size_priority=5),
            "magnet_size_priority",
        ),
    ],
)
def test_priority_order_changes_winner(monkeypatch, priorities, expected_magnet):
    monkeypatch.setattr(magnet_search, "load_search_preferences", lambda: priorities)
    result = magnet_search.search_best_magnet("Фильм")
    assert result == expected_magnet


def test_preferences_reload_between_calls(monkeypatch):
    priority_sequence = iter(
        [
            SearchPriorities(quality_priority=5, voice_priority=0, size_priority=0),
            SearchPriorities(quality_priority=0, voice_priority=5, size_priority=0),
        ]
    )

    def _load_preferences():
        return next(priority_sequence)

    monkeypatch.setattr(magnet_search, "load_search_preferences", _load_preferences)

    first_result = magnet_search.search_best_magnet("Фильм")
    second_result = magnet_search.search_best_magnet("Фильм")

    assert first_result == "magnet_quality_priority"
    assert second_result == "magnet_voice_priority"


def test_prefers_russian_voice_over_popular_non_russian_release(monkeypatch):
    monkeypatch.setattr(
        magnet_search,
        "load_search_preferences",
        lambda: SearchPriorities(quality_priority=0, voice_priority=0, size_priority=0),
    )

    result = magnet_search.search_best_magnet("Фильм")

    assert result == "magnet_voice_priority"
