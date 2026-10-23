"""Federated Learning Edge Synchronization Coordinator.
Orchestrates distributed edge node training rounds, Byzantine Multi-Krum
filtering, and (epsilon, delta)-DP noise calibration.
"""
from __future__ import annotations

import hashlib
from typing import Any
import numpy as np

from backend.federated_mesh.byzantine_krum_aggregator import ByzantineKrumAggregator
from backend.federated_mesh.dp_gaussian_accountant import GaussianDPAccountant


class EdgeSyncCoordinator:
    """Manages active federated learning rounds and node gradient submissions."""

    def __init__(self) -> None:
        self.aggregator = ByzantineKrumAggregator(f_byzantine=1)
        self.accountant = GaussianDPAccountant(max_epsilon=10.0, delta=1e-5, clip_norm=1.0, noise_multiplier=1.2)
        self.current_round = 1
        self.global_weights = np.ones(384, dtype=np.float32) * 0.05
        self.pending_submissions: dict[str, np.ndarray] = {}

    def submit_gradient(self, edge_node_id: str, round_no: int, gradient: list[float]) -> tuple[bool, float]:
        vec = np.array(gradient, dtype=np.float32)
        l2_norm = float(np.linalg.norm(vec))
        # Enforce clipping
        clipped = self.accountant.clip_gradient(vec)
        self.pending_submissions[edge_node_id] = clipped
        return True, round(l2_norm, 4)

    def execute_round(self) -> dict[str, Any]:
        """Executes Multi-Krum aggregation and DP noise addition over collected submissions."""
        if not self.pending_submissions:
            # Seed default 5 honest + 1 simulated node if none submitted yet
            for i in range(1, 6):
                honest_g = self.global_weights + np.random.normal(0, 0.01, size=384).astype(np.float32)
                self.pending_submissions[f"EDGE_NODE_0{i}"] = honest_g
            # One outlier
            self.pending_submissions["EDGE_NODE_06_POISON"] = -50.0 * self.global_weights

        node_ids = list(self.pending_submissions.keys())
        vectors = [self.pending_submissions[nid] for nid in node_ids]

        # Multi-Krum Aggregation
        krum_res = self.aggregator.aggregate(vectors)

        # Spend DP budget and add calibrated noise
        step_eps = self.accountant.spend_step()
        noisy_update = self.accountant.add_noise(krum_res.aggregated_vector)

        # Update global weights
        self.global_weights += 0.1 * noisy_update
        weights_sha = hashlib.sha256(self.global_weights.tobytes()).hexdigest()

        rejected_nodes = [node_ids[i] for i in krum_res.byzantine_indices]

        result = {
            "round_number": self.current_round,
            "participating_nodes_count": len(node_ids),
            "rejected_byzantine_count": len(rejected_nodes),
            "rejected_node_ids": rejected_nodes,
            "epsilon_spent": round(self.accountant.cumulative_epsilon, 4),
            "global_weights_sha256": weights_sha,
            "algorithm": "MULTI_KRUM_DP",
        }

        self.current_round += 1
        self.pending_submissions.clear()
        return result

    def get_status(self) -> dict[str, Any]:
        weights_sha = hashlib.sha256(self.global_weights.tobytes()).hexdigest()
        return {
            "current_round": self.current_round,
            "total_epsilon_spent": round(self.accountant.cumulative_epsilon, 4),
            "max_epsilon_budget": self.accountant.max_epsilon,
            "participating_nodes": list(self.pending_submissions.keys()),
            "last_round_sha256": weights_sha,
        }


federated_coordinator = EdgeSyncCoordinator()
