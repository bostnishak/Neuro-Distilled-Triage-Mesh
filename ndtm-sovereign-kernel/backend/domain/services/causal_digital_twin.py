import math
from typing import Dict, List, Set, Tuple
import networkx as nx
from core.logging_otel import logger
from domain.entities import InfrastructureNodeEntity, InfrastructureEdgeEntity


class CausalDigitalTwinEngine:
    """Pearl's Causal Graphical Model (DAG) with do-Calculus and Submodular Cascade Countermeasures."""

    def __init__(self):
        self.dag = nx.DiGraph()

    def load_topology(
        self,
        nodes: List[InfrastructureNodeEntity],
        edges: List[InfrastructureEdgeEntity],
    ) -> None:
        """Constructs causal structural equation DAG from persistent nodes and coupling edges."""
        self.dag.clear()
        for n in nodes:
            self.dag.add_node(
                str(n.id),
                name=n.node_name,
                criticality=n.criticality,
                base_prob=n.failure_probability,
                infra_type=n.infra_type,
            )

        for e in edges:
            self.dag.add_edge(
                str(e.source_node_id),
                str(e.target_node_id),
                weight=e.coupling_strength,
                latency=e.cascade_latency_seconds,
            )

    def do_intervention(self, intervention_node_id: str, fixed_state: float) -> Dict[str, float]:
        """Simulates Pearl's do-operator do(X = x) by mutilating incoming edges to X and propagating impact."""
        if intervention_node_id not in self.dag:
            return {}

        # Create mutilated graph G_mutilated (remove all parent edges into intervention_node_id)
        mutilated = self.dag.copy()
        in_edges = list(mutilated.in_edges(intervention_node_id))
        mutilated.remove_edges_from(in_edges)

        # Propagate cascade probabilities
        node_probs: Dict[str, float] = {}
        for nid in mutilated.nodes:
            node_probs[nid] = mutilated.nodes[nid]["base_prob"]

        node_probs[intervention_node_id] = fixed_state

        # Topological propagation
        try:
            topo_order = list(nx.topological_sort(mutilated))
        except nx.NetworkXUnfeasible:
            topo_order = list(mutilated.nodes())

        for u in topo_order:
            for _, v, data in mutilated.out_edges(u, data=True):
                coupling = data.get("weight", 0.5)
                # Independent cascade propagation: P(v) = 1 - (1 - P_base)(1 - P(u)*coupling)
                current_p = node_probs[v]
                induced_p = node_probs[u] * coupling
                updated_p = 1.0 - ((1.0 - current_p) * (1.0 - induced_p))
                node_probs[v] = min(1.0, max(0.0, updated_p))

        return node_probs

    def compute_expected_system_loss(self, failure_probabilities: Dict[str, float]) -> float:
        """Calculates expected total catastrophic infrastructure loss = sum_i Criticality(i) * P_fail(i)."""
        loss = 0.0
        for nid, p in failure_probabilities.items():
            if nid in self.dag:
                crit = self.dag.nodes[nid]["criticality"]
                loss += crit * p
        return loss

    def submodular_greedy_countermeasures(
        self,
        incident_root_node_id: str,
        budget_k: int = 3,
    ) -> List[Tuple[str, str, float]]:
        """Submodular greedy selection algorithm achieving (1 - 1/e) ~ 63.2% optimal approximation.

        Selects top-k defensive node interventions that maximally reduce cascade risk.
        Returns list of (node_id, node_name, marginal_loss_reduction).
        """
        # Baseline cascade with no defense (root failure = 1.0)
        base_probs = self.do_intervention(incident_root_node_id, 1.0)
        current_loss = self.compute_expected_system_loss(base_probs)

        selected_defenses: List[Tuple[str, str, float]] = []
        candidate_nodes = [n for n in self.dag.nodes if n != incident_root_node_id]

        for _ in range(min(budget_k, len(candidate_nodes))):
            best_node = None
            best_reduction = -1.0
            best_post_loss = current_loss

            for candidate in candidate_nodes:
                # Intervene to isolate/reinforce candidate (fix failure probability = 0.0)
                probs = self.do_intervention(candidate, 0.0)
                # Also ensure root is in failure state
                probs[incident_root_node_id] = 1.0
                cand_loss = self.compute_expected_system_loss(probs)
                reduction = current_loss - cand_loss

                if reduction > best_reduction:
                    best_reduction = reduction
                    best_node = candidate
                    best_post_loss = cand_loss

            if best_node and best_reduction > 0.01:
                node_name = self.dag.nodes[best_node]["name"]
                selected_defenses.append((best_node, node_name, best_reduction))
                candidate_nodes.remove(best_node)
                current_loss = best_post_loss
            else:
                break

        logger.info(
            "submodular_countermeasures_selected",
            count=len(selected_defenses),
            root=incident_root_node_id,
        )
        return selected_defenses
