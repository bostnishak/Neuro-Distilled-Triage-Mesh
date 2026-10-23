"""Critic Filter evaluating synthetic dataset quality, token length, and lexical relevance."""
from __future__ import annotations

from typing import Any

from ml_pipeline.synthetic_generator import TAXONOMY_CATEGORIES


class CriticDatasetFilter:
    """Quality gate validating synthetically generated samples prior to student distillation."""

    def __init__(self, min_words: int = 6, max_words: int = 150) -> None:
        self.min_words = min_words
        self.max_words = max_words

    def filter_samples(
        self, samples: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for sample in samples:
            text = sample.get("text", "").strip()
            category = sample.get("category", "")
            urgency = sample.get("urgency_score", 0)

            words = text.split()
            if len(words) < self.min_words:
                rejected.append({**sample, "rejection_reason": "TEXT_TOO_SHORT"})
                continue

            if len(words) > self.max_words:
                rejected.append({**sample, "rejection_reason": "TEXT_TOO_LONG"})
                continue

            if category not in TAXONOMY_CATEGORIES:
                rejected.append({**sample, "rejection_reason": "INVALID_CATEGORY"})
                continue

            if not (1 <= urgency <= 10):
                rejected.append({**sample, "rejection_reason": "INVALID_URGENCY_RANGE"})
                continue

            accepted.append(sample)

        return accepted, rejected
