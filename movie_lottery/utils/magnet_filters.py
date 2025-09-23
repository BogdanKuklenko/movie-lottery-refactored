"""Utilities for categorising voiceover information in release names."""
from __future__ import annotations

from typing import Iterable

FULL_DUB_KEYWORDS: tuple[str, ...] = (
    "полный дубляж",
    "полное дублирование",
    "full dub",
    "full dubbing",
    "professional dubbing",
)

RUSSIAN_VOICE_KEYWORDS: tuple[str, ...] = (
    "профессионал",
    "многоголос",
    "двуголос",
    "двухголос",
    "одноголос",
    "закадров",
    "русск",
    "озвуч",
    "локализ",
    "voiceover",
    "russian",
    "dub",
)

NON_RUSSIAN_KEYWORDS: tuple[str, ...] = (
    "без перевода",
    "оригинал",
    "original audio",
    "no voice",
    "no voiceover",
    "no translation",
)

QUALITY_KEYWORDS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (0, ("1080p", "1080")),
    (1, ("2160p", "2160", "4k")),
    (2, ("720p", "720")),
    (3, ("480p", "480")),
)

DEFAULT_VOICE_RANK = -1
DEFAULT_QUALITY_RANK = 5


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_voiceover(name: str) -> tuple[int, int]:
    """Classify the voiceover quality present in *name*.

    Returns
    -------
    tuple[int, int]
        ``(voice_rank, quality_rank)`` where ``voice_rank`` is ``0`` for full
        dubbing, positive for other types of Russian voiceovers, and negative
        when no Russian voiceover markers are present. ``quality_rank`` is used
        as a secondary tie-breaker with lower values indicating higher quality.
    """

    normalized = (name or "").lower()
    if not normalized.strip():
        return DEFAULT_VOICE_RANK, DEFAULT_QUALITY_RANK

    if _contains_any(normalized, NON_RUSSIAN_KEYWORDS):
        voice_rank = -1
    elif _contains_any(normalized, FULL_DUB_KEYWORDS):
        voice_rank = 0
    elif _contains_any(normalized, RUSSIAN_VOICE_KEYWORDS):
        voice_rank = 1
    else:
        voice_rank = DEFAULT_VOICE_RANK

    quality_rank = DEFAULT_QUALITY_RANK
    for rank, keywords in QUALITY_KEYWORDS:
        if _contains_any(normalized, keywords):
            quality_rank = rank
            break

    return voice_rank, quality_rank
