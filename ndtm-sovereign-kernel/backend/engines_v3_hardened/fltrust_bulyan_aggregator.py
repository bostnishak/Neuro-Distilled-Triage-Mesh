"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Phase 30: FLTrust + Bulyan Hybrid Byzantine-Resilient Aggregator
Combines Server-Anchor Cosine Trust Scoring, Bulyan Coordinate-Wise Trimmed Median,
and Rényi Differential Privacy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np


@dataclass
class FederatedClientUpdate:
    client_id: str
    gradient: np.ndarray  # shape (d,)
    sample_count: int
    reported_loss: float = 0.0


@dataclass
class ByzantineAggregationResult:
    aggregated_gradient: np.ndarray
    total_clients_submitted: int
    trusted_clients_count: int
    byzantine_clients_detected: List[str]
    client_trust_scores: Dict[str, float]
    dp_noise_added_norm: float
    is_resilient: bool


class FLTrustBulyanAggregator:
    """
    Sovereign Federated Learning Aggregator immune to both:
    1. Directional Byzantine drift (via FLTrust server anchor gradient g_0).
    2. Subtle colluding Byzantine variance attacks (via Bulyan trimmed median).
    """

    def __init__(
        self,
        dimension: int = 128,
        byzantine_tolerance_fraction: float = 0.25,
        dp_clipping_bound_c: float = 1.0,
        dp_noise_multiplier_sigma: float = 0.01,
        trust_threshold_min: float = 0.05,
    ):
        self.d = dimension
        self.f_frac = byzantine_tolerance_fraction
        self.c_clip = dp_clipping_bound_c
        self.sigma = dp_noise_multiplier_sigma
        self.trust_min = trust_threshold_min

    def aggregate(
        self,
        client_updates: List[FederatedClientUpdate],
        server_anchor_gradient: np.ndarray,
    ) -> ByzantineAggregationResult:
        """
        Executes robust FLTrust + Bulyan aggregation cycle.
        
        Args:
            client_updates: List of client gradient updates.
            server_anchor_gradient: Clean gradient g_0 evaluated on server validation dataset.
        """
        K = len(client_updates)
        if K == 0:
            return ByzantineAggregationResult(
                aggregated_gradient=np.zeros(self.d, dtype=np.float64),
                total_clients_submitted=0,
                trusted_clients_count=0,
                byzantine_clients_detected=[],
                client_trust_scores={},
                dp_noise_added_norm=0.0,
                is_resilient=True,
            )

        g0 = np.asarray(server_anchor_gradient, dtype=np.float64).flatten()
        norm_g0 = float(np.linalg.norm(g0))
        if norm_g0 < 1e-8:
            norm_g0 = 1.0
            g0 = np.ones_like(g0) * (1.0 / math.sqrt(self.d))

        # =================================================================
        # STEP 1: FLTrust Cosine Scoring & Magnitude Normalization
        # =================================================================
        trust_scores: Dict[str, float] = {}
        normalized_updates: List[np.ndarray] = []
        valid_client_indices: List[int] = []
        byzantine_detected: List[str] = []

        for idx, client in enumerate(client_updates):
            gk = np.asarray(client.gradient, dtype=np.float64).flatten()
            norm_gk = float(np.linalg.norm(gk))

            if norm_gk < 1e-12:
                # Dead or zero gradient
                trust_scores[client.client_id] = 0.0
                byzantine_detected.append(client.client_id)
                continue

            # Cosine similarity: <gk, g0> / (||gk|| * ||g0||)
            cos_sim = float(np.dot(gk, g0) / (norm_gk * norm_g0))

            # ReLU clipping: negative cosine indicates adversarial direction
            ts = max(0.0, cos_sim)
            trust_scores[client.client_id] = round(ts, 4)

            if ts < self.trust_min:
                byzantine_detected.append(client.client_id)
            else:
                # Normalized update scaled by trust score: u_k = TS * (||g0|| / ||gk||) * gk
                u_k = ts * (norm_g0 / norm_gk) * gk
                normalized_updates.append(u_k)
                valid_client_indices.append(idx)

        M = len(normalized_updates)
        if M == 0:
            # Complete adversarial swarm; fall back exclusively to trusted server anchor
            return ByzantineAggregationResult(
                aggregated_gradient=g0,
                total_clients_submitted=K,
                trusted_clients_count=0,
                byzantine_clients_detected=[c.client_id for c in client_updates],
                client_trust_scores=trust_scores,
                dp_noise_added_norm=0.0,
                is_resilient=False,
            )

        # If too few candidates remain for Bulyan selection, use FLTrust weighted average
        if M <= 3:
            total_ts = sum(trust_scores[client_updates[i].client_id] for i in valid_client_indices)
            agg = np.zeros(self.d, dtype=np.float64)
            for u in normalized_updates:
                agg += u
            agg = agg / max(1e-8, total_ts)

            # Apply DP noise
            agg_clipped, noise_norm = self._apply_differential_privacy(agg, M)
            return ByzantineAggregationResult(
                aggregated_gradient=agg_clipped,
                total_clients_submitted=K,
                trusted_clients_count=M,
                byzantine_clients_detected=byzantine_detected,
                client_trust_scores=trust_scores,
                dp_noise_added_norm=noise_norm,
                is_resilient=True,
            )

        # =================================================================
        # STEP 2: Bulyan Selection with Coordinate-Wise Trimmed Median
        # =================================================================
        # Assumed Byzantine count f in candidate pool
        f = max(1, int(math.floor(self.f_frac * M)))
        # Bulyan condition requires M >= 4f + 3; if smaller, clamp f
        if 4 * f + 3 > M:
            f = max(0, (M - 3) // 4)

        if f == 0:
            # Small pool: standard coordinate-wise median
            U_mat = np.stack(normalized_updates, axis=0)  # shape (M, d)
            bulyan_grad = np.median(U_mat, axis=0)
        else:
            # Multi-Krum pre-selection of size theta = M - 2f
            theta = max(1, M - 2 * f)
            U_mat = np.stack(normalized_updates, axis=0)  # shape (M, d)

            # Pairwise Euclidean distances: D_mat (M, M)
            diffs = U_mat[:, np.newaxis, :] - U_mat[np.newaxis, :, :]
            dist_sq = np.sum(diffs ** 2, axis=-1)

            # For each vector, sum distances to its (M - f - 2) closest neighbors
            krum_scores = np.zeros(M, dtype=np.float64)
            nb_count = max(1, M - f - 2)
            for i in range(M):
                sorted_dists = np.sort(dist_sq[i])
                krum_scores[i] = np.sum(sorted_dists[1 : nb_count + 1])

            # Select theta vectors with lowest Krum scores
            best_indices = np.argsort(krum_scores)[:theta]
            selected_subpool = U_mat[best_indices]  # shape (theta, d)

            # Coordinate-wise trimmed median on selected subpool
            # Trim beta = max(1, f) lowest and highest values per coordinate
            beta = max(1, min(f, (theta - 1) // 2))
            bulyan_grad = np.zeros(self.d, dtype=np.float64)

            for col in range(self.d):
                col_vals = np.sort(selected_subpool[:, col])
                if len(col_vals) > 2 * beta:
                    trimmed = col_vals[beta : len(col_vals) - beta]
                    bulyan_grad[col] = np.mean(trimmed)
                else:
                    bulyan_grad[col] = np.median(col_vals)

        # =================================================================
        # STEP 3: Rényi Differential Privacy (DP) Gaussian Mechanism
        # =================================================================
        agg_final, noise_norm = self._apply_differential_privacy(bulyan_grad, M)

        return ByzantineAggregationResult(
            aggregated_gradient=agg_final,
            total_clients_submitted=K,
            trusted_clients_count=M,
            byzantine_clients_detected=byzantine_detected,
            client_trust_scores=trust_scores,
            dp_noise_added_norm=noise_norm,
            is_resilient=True,
        )

    def _apply_differential_privacy(self, grad: np.ndarray, client_count: int) -> Tuple[np.ndarray, float]:
        """Clips gradient L2 norm to C and adds calibrated Gaussian noise."""
        g_norm = float(np.linalg.norm(grad))
        clip_factor = min(1.0, self.c_clip / max(1e-8, g_norm))
        clipped_grad = grad * clip_factor

        # Noise scale: sigma * C / client_count
        noise_std = (self.sigma * self.c_clip) / max(1, client_count)
        rng = np.random.RandomState()
        noise = rng.normal(0.0, noise_std, size=self.d)

        noisy_grad = clipped_grad + noise
        noise_norm = float(np.linalg.norm(noise))
        return noisy_grad, round(noise_norm, 6)
