"""Causal Digital Twin API Router (NDTM v2.0).
Provides endpoints for topological inspection, cascade failure blast-radius simulation,
and Judea Pearl's do-calculus counterfactual structural interventions.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from backend.causal_twin.blast_radius_simulator import BlastRadiusSimulator
from backend.causal_twin.counterfactual_engine import CounterfactualEngine
from backend.causal_twin.topology_graph import (
    CausalTopologyGraph,
    ISTANBUL_INFRASTRUCTURE_EDGES,
    ISTANBUL_INFRASTRUCTURE_NODES,
)
from backend.schemas.v2_schemas import (
    CascadeNodeImpact,
    CascadeSimulationRequest,
    CascadeSimulationResponse,
    CounterfactualInterventionRequest,
    CounterfactualInterventionResponse,
    InfraEdgeDTO,
    InfraNodeDTO,
    TopologyResponse,
)

logger = logging.getLogger("api.causal_twin")
router = APIRouter(prefix="/causal", tags=["Causal Digital Twin"])

topology_graph = CausalTopologyGraph()
simulator = BlastRadiusSimulator(topology_graph)
counterfactual_engine = CounterfactualEngine(topology_graph)


@router.get("/topology", response_model=TopologyResponse)
async def get_infrastructure_topology() -> TopologyResponse:
    """Returns the canonical 12 critical infrastructure nodes and 18 directed coupling edges."""
    nodes = [
        InfraNodeDTO(
            id=f"node-{n.node_code.lower()}",
            node_code=n.node_code,
            node_type=n.node_type,
            latitude=n.latitude,
            longitude=n.longitude,
            base_failure_prob=n.base_failure_prob,
            current_health_score=n.current_health_score,
            capacity_kw=n.capacity_kw,
            metadata=n.metadata,
        )
        for n in ISTANBUL_INFRASTRUCTURE_NODES
    ]
    edges = [
        InfraEdgeDTO(
            source_code=e.source_code,
            target_code=e.target_code,
            dependency_weight=e.dependency_weight,
            propagation_delay_minutes=e.propagation_delay_minutes,
            coupling_type=e.coupling_type,
        )
        for e in ISTANBUL_INFRASTRUCTURE_EDGES
    ]
    return TopologyResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
    )


@router.post("/simulate", response_model=CascadeSimulationResponse)
async def simulate_cascade_blast_radius(
    req: CascadeSimulationRequest,
) -> CascadeSimulationResponse:
    """Simulates multi-hop cascade failure progression from root node and computes Cumulative Risk Rating (CRR)."""
    try:
        res = simulator.simulate_cascade(
            root_node_code=req.failed_node_code,
            time_horizon_minutes=req.time_horizon_minutes,
        )
        timeline = [
            CascadeNodeImpact(
                node_code=item["node_code"],
                failure_probability=item["failure_probability"],
                time_to_fail_minutes=item["time_to_fail_minutes"],
                coupling_path=item["coupling_path"],
            )
            for item in res["cascade_timeline"]
        ]
        return CascadeSimulationResponse(
            root_failed_node=res["root_failed_node"],
            cascade_timeline=timeline,
            cumulative_risk_rating=res["cumulative_risk_rating"],
            affected_nodes_count=res["affected_nodes_count"],
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(val_err),
        )


@router.post("/counterfactual", response_model=CounterfactualInterventionResponse)
async def evaluate_counterfactual_intervention(
    req: CounterfactualInterventionRequest,
) -> CounterfactualInterventionResponse:
    """Evaluates Judea Pearl's do-calculus intervention do(X = x) on mutilated topology."""
    try:
        res = counterfactual_engine.evaluate_intervention(
            failed_node_code=req.failed_node_code,
            intervened_node_code=req.intervened_node_code,
            intervention_action=req.intervention_action,
        )
        return CounterfactualInterventionResponse(
            original_risk_rating=res["original_risk_rating"],
            counterfactual_risk_rating=res["counterfactual_risk_rating"],
            delta_crr=res["delta_crr"],
            mutilated_edges_severed=res["mutilated_edges_severed"],
            is_risk_mitigated=res["is_risk_mitigated"],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Causal evaluation failed: {exc}",
        )
