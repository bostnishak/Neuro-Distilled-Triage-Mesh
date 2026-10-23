"""Blast-Radius Cascade Failure Simulation Engine.
Computes probabilistic cascade propagation through topological coupling paths
and calculates Cumulative Risk Rating (CRR).
"""
from __future__ import annotations

import heapq
from typing import Any

from backend.causal_twin.topology_graph import (
    CausalTopologyGraph,
    EdgeDefinition,
)


class BlastRadiusSimulator:
    """Simulates cascade failure propagation along directed structural dependencies."""

    def __init__(self, graph: CausalTopologyGraph | None = None) -> None:
        self.graph = graph or CausalTopologyGraph()

    def simulate_cascade(
        self,
        root_node_code: str,
        time_horizon_minutes: int = 60,
    ) -> dict[str, Any]:
        """Calculates probabilistic cascade timeline using Dijkstra-like earliest propagation."""
        root = self.graph.get_node(root_node_code)
        if not root:
            raise ValueError(f"Root node code '{root_node_code}' not found in topology.")

        # Priority queue entries: (time_to_fail, failure_prob, current_node, path)
        pq: list[tuple[int, float, str, list[str]]] = [(0, 1.0, root_node_code, [root_node_code])]
        visited_probs: dict[str, float] = {root_node_code: 1.0}
        earliest_time: dict[str, int] = {root_node_code: 0}
        best_path: dict[str, list[str]] = {root_node_code: [root_node_code]}

        while pq:
            curr_time, curr_prob, curr_node, path = heapq.heappop(pq)

            if curr_time > time_horizon_minutes:
                continue

            for edge in self.graph.get_outgoing_edges(curr_node):
                nxt = edge.target_code
                arr_time = curr_time + edge.propagation_delay_minutes
                nxt_prob = curr_prob * edge.dependency_weight

                if arr_time <= time_horizon_minutes:
                    prev_best_prob = visited_probs.get(nxt, 0.0)
                    if nxt_prob > prev_best_prob:
                        visited_probs[nxt] = round(nxt_prob, 4)
                        earliest_time[nxt] = arr_time
                        best_path[nxt] = path + [nxt]
                        heapq.heappush(pq, (arr_time, nxt_prob, nxt, best_path[nxt]))

        # Format cascade timeline ordered by time
        timeline: list[dict[str, Any]] = []
        cumulative_risk = 0.0

        for node_code, prob in sorted(visited_probs.items(), key=lambda x: earliest_time[x[0]]):
            t = earliest_time[node_code]
            p = best_path[node_code]
            node_def = self.graph.get_node(node_code)
            capacity = (node_def.capacity_kw if node_def and node_def.capacity_kw else 10000.0) / 100000.0
            node_weight = 1.0 + capacity

            risk_contribution = prob * node_weight
            cumulative_risk += risk_contribution

            timeline.append({
                "node_code": node_code,
                "failure_probability": prob,
                "time_to_fail_minutes": t,
                "coupling_path": p,
            })

        return {
            "root_failed_node": root_node_code,
            "cascade_timeline": timeline,
            "cumulative_risk_rating": round(cumulative_risk, 3),
            "affected_nodes_count": len(timeline),
        }
