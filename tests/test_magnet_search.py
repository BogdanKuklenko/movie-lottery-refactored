"""Tests for magnet search utilities with DHT fallback."""

from __future__ import annotations

import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _prepare_package_stubs() -> None:
    if "movie_lottery" in sys.modules:
        return

    session_stub = types.SimpleNamespace(
        add=lambda *_: None,
        commit=lambda: None,
        rollback=lambda: None,
    )
    db_stub = types.SimpleNamespace(session=session_stub)

    movie_lottery_pkg = types.ModuleType("movie_lottery")
    movie_lottery_pkg.__path__ = [str(PROJECT_ROOT / "movie_lottery")]
    movie_lottery_pkg.db = db_stub
    sys.modules["movie_lottery"] = movie_lottery_pkg

    models_module = types.ModuleType("movie_lottery.models")

    class _QueryStub:
        def get(self, _):  # pragma: no cover - used only implicitly
            return None

    class _MovieIdentifierStub:
        query = _QueryStub()

        def __init__(self, kinopoisk_id: int, magnet_link: str):
            self.kinopoisk_id = kinopoisk_id
            self.magnet_link = magnet_link

    models_module.MovieIdentifier = _MovieIdentifierStub
    sys.modules["movie_lottery.models"] = models_module


_prepare_package_stubs()

from movie_lottery.utils import magnet_search  # noqa: E402  # pylint: disable=wrong-import-position


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - behaviour is trivial
        return None

    def json(self):  # pragma: no cover - behaviour is trivial
        return self._payload


@pytest.mark.parametrize("http_payload", [[], {"results": []}])
def test_search_best_magnet_uses_dht_when_http_empty(http_payload):
    """Ensure DHT fallback supplies a magnet link when HTTP search fails."""

    session = MagicMock()
    session.get.return_value = _DummyResponse(http_payload)

    info_hash = "A" * 40
    dht_result = {
        "name": "Фильм (2024) 1080p полный дубляж",
        "info_hash": info_hash,
        "seeders": 321,
    }

    with patch.object(magnet_search, "search_via_dht", return_value=[dht_result]) as dht_mock:
        magnet = magnet_search.search_best_magnet("Фильм", session=session)

    assert magnet == magnet_search._build_magnet(info_hash.lower(), dht_result["name"])
    session.get.assert_called_once()
    dht_mock.assert_called_once()
