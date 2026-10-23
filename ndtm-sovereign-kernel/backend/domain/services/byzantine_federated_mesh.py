import math
from typing import Dict, List, Tuple, Optional
import numpy as np
from core.exceptions import ByzantineFaultDetectedException
from core.logging_otel import logger
from domain.value_objects import DifferentialPrivacyBudget


class ByzantineFederatedMesh:
    """Byzantine-Fault-Tolerant Federated Aggregation via Multi-Krum and Rényi Differential Privacy."""

    @staticmethod
    def multi_krum(
        node_ids: List[str],
        gradients: List[np.ndarray],
        byzantine_tolerance_f: int = 1,
        retained_k: Optional[int] = None,
    ) -> Tuple[np.ndarray, List[str], List[float]]:
        """Executes Multi-Krum aggregation.

        m = total nodes. Assumes 2*f + 2 < m.
        Returns (aggregated_gradient, byzantine_node_ids, krum_scores).
        """
        m = len(gradients)
        if m == 0:
            raise ValueError("No gradient updates provided to Multi-Krum")
        if m <= 2:
            # Fallback simple average if insufficient nodes for Krum bound
            avg_grad = np.mean(gradients, axis=0)
            return avg_grad, [], [0.0] * m

        # Ensure valid byzantine bound
        f = min(byzantine_tolerance_f, max(1, (m - 3) // 2))
        k = retained_k or (m - f)
        k = max(1, min(k, m - f))

        # 1. Compute pairwise squared Euclidean distances: D[i][j] = ||w_i - w_j||^2
        dist_matrix = np.zeros((m, m), dtype=np.float64)
        for i in range(m):
            for j in range(i + 1, m):
                d = float(np.sum((gradients[i] - gradients[j]) ** 2))
                dist_matrix[i, j] = d
                dist_matrix[j, i] = d

        # 2. For each vector i, sum distances to its (m - f - 2) closest neighbors
        num_neighbors = max(1, m - f - 2)
        scores = []
        for i in range(m):
            # Sort distances for row i excluding itself
            sorted_dists = np.sort(dist_matrix[i, :])
            # Skip dist to itself (index 0 is 0.0)
            neighbor_sum = float(np.sum(sorted_dists[1 : 1 + num_neighbors]))
            scores.append(neighbor_sum)

        # 3. Rank indices by Krum score ascending (lowest score = highest agreement with honest majority)
        ranked_indices = np.argsort(scores)

        selected_indices = ranked_indices[:k]
        pruned_indices = ranked_indices[m - f :]

        byzantine_nodes = [node_ids[idx] for idx in pruned_indices]
        if byzantine_nodes:
            logger.warning("byzantine_nodes_pruned_by_multi_krum", pruned=byzantine_nodes)

        # 4. Compute aggregate mean of honest selected gradients
        selected_gradients = [gradients[idx] for idx in selected_indices]
        aggregated_gradient = np.mean(selected_gradients, axis=0)

        return aggregated_gradient, byzantine_nodes, scores

    @staticmethod
    def apply_renyi_dp_noise(
        gradient_vector: np.ndarray,
        l2_clip_norm: float = 1.0,
        dp_budget: Optional[DifferentialPrivacyBudget] = None,
    ) -> Tuple[np.ndarray, float]:
        """Clips L2 gradient norm and injects calibrated Gaussian differential privacy noise.

        Returns (privatized_gradient, accumulated_renyi_epsilon).
        """
        budget = dp_budget or DifferentialPrivacyBudget(epsilon=1.5, delta=1e-5, alpha=4.0)

        # 1. L2 Norm Clipping
        current_norm = float(np.linalg.norm(gradient_vector))
        if current_norm > l2_clip_norm:
            clipped_gradient = gradient_vector * (l2_clip_norm / current_norm)
        else:
            clipped_gradient = gradient_vector.copy()

        # 2. Compute noise scale sigma using (alpha, epsilon) RDP accountant
        # sigma = (l2_clip_norm * sqrt(alpha / (2 * epsilon)))
        sigma = l2_clip_norm * math.sqrt(budget.alpha / (2.0 * budget.epsilon))

        # 3. Inject Gaussian noise
        noise = np.random.normal(0.0, sigma, size=clipped_gradient.shape).astype(np.float32)
        privatized = clipped_gradient + noise

        # RDP expenditure = alpha / (2 * (sigma / l2_clip_norm)^2)
        rdp_expenditure = budget.alpha / (2.0 * ((sigma / l2_clip_norm) ** 2))

        return privatized, rdp_expenditure
