"""Utilities for loading magnet search priority preferences."""

from __future__ import annotations

from dataclasses import dataclass

from flask import has_app_context

from ..models import SearchPreference


@dataclass(frozen=True)
class SearchPriorities:
    """Container for user-configurable search priorities."""

    quality_priority: int = 0
    voice_priority: int = 0
    size_priority: int = 0
    auto_search_enabled: bool = True


def load_search_preferences() -> SearchPriorities:
    """Load search priorities from the database, falling back to defaults.

    Returns
    -------
    SearchPriorities
        The configured priorities for quality, voice and size weighting. When
        no configuration is available (or when the function is invoked outside
        of a Flask application context) all priorities default to ``0`` which
        effectively disables preference-based sorting for that category.
    """

    if not has_app_context():
        return SearchPriorities()

    preference = SearchPreference.query.get(1)
    if preference is None:
        return SearchPriorities()

    return SearchPriorities(
        quality_priority=int(preference.quality_priority or 0),
        voice_priority=int(preference.voice_priority or 0),
        size_priority=int(preference.size_priority or 0),
        auto_search_enabled=bool(
            preference.auto_search_enabled
            if preference.auto_search_enabled is not None
            else True
        ),
    )

