"""Tests for the auto search toggle behaviour."""

from __future__ import annotations

import importlib
import pathlib
import sys
import types

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if "flask_migrate" not in sys.modules:
    flask_migrate = types.ModuleType("flask_migrate")
    flask_migrate.Migrate = lambda *args, **kwargs: None
    sys.modules["flask_migrate"] = flask_migrate


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "auto-search.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    for module_name in list(sys.modules):
        if module_name.startswith("movie_lottery"):
            sys.modules.pop(module_name)

    movie_lottery = importlib.import_module("movie_lottery")
    application = movie_lottery.create_app()
    application.config.update(TESTING=True)

    yield application

    with application.app_context():
        movie_lottery.db.session.remove()
        movie_lottery.db.drop_all()

    for module_name in list(sys.modules):
        if module_name.startswith("movie_lottery"):
            sys.modules.pop(module_name)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def search_priorities_cls(app):
    module = importlib.import_module("movie_lottery.utils.search_preferences")
    return module.SearchPriorities


@pytest.mark.parametrize(
    ("auto_search_enabled", "expected_calls"),
    [
        (False, 0),
        (True, 2),
    ],
)
def test_create_lottery_respects_auto_search(
    monkeypatch,
    client,
    search_priorities_cls,
    auto_search_enabled,
    expected_calls,
):
    start_calls: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(
        "movie_lottery.routes.api_routes.start_background_search",
        lambda *args, **kwargs: start_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "movie_lottery.routes.api_routes.load_search_preferences",
        lambda: search_priorities_cls(auto_search_enabled=auto_search_enabled),
    )

    response = client.post(
        "/api/create",
        json={
            "movies": [
                {"name": "Фильм 1", "year": "2020", "kinopoisk_id": 101},
                {"name": "Фильм 2", "year": "2021", "kinopoisk_id": 202},
            ]
        },
    )

    assert response.status_code == 200
    assert len(start_calls) == expected_calls


@pytest.mark.parametrize(
    ("auto_search_enabled", "expected_calls"),
    [
        (False, 0),
        (True, 1),
    ],
)
def test_library_add_respects_auto_search(
    monkeypatch,
    client,
    search_priorities_cls,
    auto_search_enabled,
    expected_calls,
):
    start_calls: list[tuple[tuple, dict]] = []

    monkeypatch.setattr(
        "movie_lottery.routes.api_routes.start_background_search",
        lambda *args, **kwargs: start_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "movie_lottery.routes.api_routes.load_search_preferences",
        lambda: search_priorities_cls(auto_search_enabled=auto_search_enabled),
    )

    response = client.post(
        "/api/library",
        json={
            "movie": {
                "name": "Фильм библиотека",
                "year": "2022",
                "kinopoisk_id": 303,
            }
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(start_calls) == expected_calls
