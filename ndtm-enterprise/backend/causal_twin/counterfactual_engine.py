"""Pearl's Do-Calculus Counterfactual Intervention Engine.
Implements structural causal interventions do(X = x) on mutilated graphs G_{X-bar}
by severing incoming edges and verifying downstream risk mitigation (Delta CRR > 0).
"""
from __future__ import annotations

from typing import Any

from backend.causal_twin.blast_radius_simulator import BlastRadiusSimulator
from backend.causal_twin.topology_graph import CausalTopologyGraph


class CounterfactualEngine:
    """Evaluates causal interventional queries using Judea Pearl's structural do-calculus."""

    def __init__(self, graph: CausalTopologyGraph | None = None) -> None:
        self.graph = graph or CausalTopologyGraph()
        self.base_simulator = BlastRadiusSimulator(self.graph)

    def evaluate_intervention(
        self,
        failed_node_code: str,
        intervened_node_code: str,
        intervention_action: str = "REINFORCED",
    ) -> dict[str, Any]:
        """Calculates P(downstream | do(intervened_node = REINFORCED), failed_node).

        1. Observational baseline: Run cascade simulation on G.
        2. Mutilation: Sever all incoming edges into intervened_node_code (G_{X-bar}).
        3. Intervention: Set intervened_node to reinforced state (e.g. failure prob reduced).
        4. Measure Delta CRR = CRR_baseline - CRR_intervention.
        """
        # 1. Observational cascade
        baseline_sim = self.base_simulator.simulate_cascade(failed_node_code)
        baseline_crr = baseline_sim["cumulative_risk_rating"]

        # 2. Mutilate graph: sever all incoming edges to intervened_node_code
        incoming_edges = self.graph.get_incoming_edges(intervened_node_code)
        severed_edges_desc = [
            f"{e.source_code} -> {e.target_code} ({e.coupling_type})"
            for e in incoming_edges
        ]
        mutilated_graph = self.graph.clone_mutilated(intervened_node_code)

        # 3. Interventional simulation on mutilated graph
        interventional_sim = BlastRadiusSimulator(mutilated_graph).simulate_cascade(failed_node_code)
        counterfactual_crr = interventional_sim["cumulative_risk_rating"]

        # If intervened node was downstream, its probability of failure is mitigated
        delta_crr = round(baseline_crr - counterfactual_crr, 3)
        if delta_crr < 0.0:
            delta_crr = 0.0

        return {
            "original_risk_rating": baseline_crr,
            "counterfactual_risk_rating": counterfactual_crr,
            "delta_crr": delta_crr,
            "mutilated_edges_severed": severed_edges_desc,
            "is_risk_mitigated": delta_crr > 0.0,
        }
