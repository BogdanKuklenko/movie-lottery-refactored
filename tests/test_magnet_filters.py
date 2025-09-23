"""Tests for voiceover classification utilities."""

from __future__ import annotations

import importlib.util
import pathlib


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "movie_lottery" / "utils" / "magnet_filters.py"

spec = importlib.util.spec_from_file_location("magnet_filters", MODULE_PATH)
assert spec and spec.loader is not None
magnet_filters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(magnet_filters)

classify_voiceover = magnet_filters.classify_voiceover


def test_full_dubbing_has_highest_priority():
    voice_rank, quality_rank = classify_voiceover(
        "Фильм (2024) WEB-DL 1080p Полное дублирование"
    )
    assert voice_rank == 0
    assert quality_rank == 0


def test_professional_multivoice_classification():
    voice_rank, quality_rank = classify_voiceover(
        "Фильм 2023 Профессиональный многоголосый перевод 720p"
    )
    assert voice_rank == 1
    assert quality_rank == 2


def test_no_translation_is_not_russian():
    voice_rank, quality_rank = classify_voiceover("Film 2024 без перевода")
    assert voice_rank < 0
    assert quality_rank == 5
