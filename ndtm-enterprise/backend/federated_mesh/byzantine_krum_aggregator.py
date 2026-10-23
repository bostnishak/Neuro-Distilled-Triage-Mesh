"""Byzantine-Resilient Multi-Krum Aggregator.
Implements the Blanchard et al. Multi-Krum protocol for provable Byzantine resilience
in distributed federated gradient aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(slots=True)
class KrumResult:
    aggregated_vector: np.ndarray
    selected_indices: list[int]
    byzantine_indices: list[int]
    scores: dict[int, float]


class ByzantineKrumAggregator:
    """Aggregates distributed gradient updates while rejecting Byzantine poisoners."""

    def __init__(self, f_byzantine: int = 1) -> None:
        self.f = f_byzantine

    def aggregate(
        self,
        vectors: list[np.ndarray],
        m_selected: int | None = None,
    ) -> KrumResult:
        n = len(vectors)
        if n < 2 * self.f + 3:
            # Fallback if n is too small for theoretical bounds: require at least n > f
            if n <= self.f:
                raise ValueError(f"Insufficient nodes: n={n} <= f={self.f}")

        # Compute pairwise squared Euclidean distances
        dists = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = float(np.sum((vectors[i] - vectors[j]) ** 2))
                dists[i, j] = d
                dists[j, i] = d

        # Compute Krum score for each vector: sum of (n - f - 2) smallest distances
        # If n - f - 2 < 1, use 1
        k_neighbors = max(1, n - self.f - 2)
        scores: dict[int, float] = {}

        for i in range(n):
            sorted_dists = np.sort(dists[i, :])
            # Exclude distance to itself (index 0 which is 0.0)
            scores[i] = float(np.sum(sorted_dists[1 : k_neighbors + 1]))

        # Sort indices by score ascending (lowest score = most representative honest vector)
        sorted_indices = sorted(scores.keys(), key=lambda idx: scores[idx])

        # Multi-Krum selects top m vectors (default: n - f)
        m = m_selected or max(1, n - self.f)
        selected_idx = sorted_indices[:m]
        byzantine_idx = sorted_indices[m:]

        # Compute mean of selected honest vectors
        selected_vectors = [vectors[i] for i in selected_idx]
        aggregated = np.mean(selected_vectors, axis=0)

        return KrumResult(
            aggregated_vector=aggregated,
            selected_indices=selected_idx,
            byzantine_indices=byzantine_idx,
            scores=scores,
        )
