"""Scoring utilities for evaluating magnet search candidates."""

from __future__ import annotations


QUALITY_RANK_TO_SCORE = {
    0: 3,  # 1080p
    1: 2,  # 2160p / 4K
    2: 1,  # 720p
}


def score_quality(quality_rank: int) -> int:
    """Convert ``classify_voiceover`` quality ranks into scoring weights."""

    return QUALITY_RANK_TO_SCORE.get(quality_rank, 0)


def score_voice_category(voice_rank: int) -> int:
    """Return a normalised score for the detected voice category."""

    if voice_rank == 0:
        return 2
    if voice_rank > 0:
        return 1
    return 0


def score_size(size: int) -> int:
    """Return a score that prefers smaller payload sizes."""

    if size <= 0:
        return 0
    return -size

