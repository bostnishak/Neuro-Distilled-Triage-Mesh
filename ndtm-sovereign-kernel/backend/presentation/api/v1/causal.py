from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_db
from infrastructure.database.orm_models import InfrastructureNodeOrm, InfrastructureEdgeOrm, UserOrm
from presentation.api.dependencies import get_current_user
from domain.services.causal_digital_twin import CausalDigitalTwinEngine
from domain.entities import InfrastructureNodeEntity, InfrastructureEdgeEntity
from domain.value_objects import GeoCoordinates

router = APIRouter(prefix="/causal", tags=["Pearl's Causal Digital Twin"])
_causal_engine = CausalDigitalTwinEngine()


class InterveneRequest(BaseModel):
    node_id: str
    fixed_state: float = Field(..., ge=0.0, le=1.0)


class CountermeasureRequest(BaseModel):
    root_node_id: str
    budget_k: int = Field(default=3, ge=1, le=10)


async def _load_engine_topology(session: AsyncSession) -> None:
    """Loads all infrastructure nodes and directed coupling edges into networkx DAG."""
    nodes_res = await session.execute(
        select(
            InfrastructureNodeOrm.id,
            InfrastructureNodeOrm.node_name,
            InfrastructureNodeOrm.infra_type,
            InfrastructureNodeOrm.criticality,
            InfrastructureNodeOrm.failure_probability,
            InfrastructureNodeOrm.created_at,
            func.ST_X(InfrastructureNodeOrm.location).label("lon"),
            func.ST_Y(InfrastructureNodeOrm.location).label("lat"),
        )
    )
    node_rows = nodes_res.fetchall()

    edges_res = await session.execute(select(InfrastructureEdgeOrm))
    edge_rows = edges_res.scalars().all()

    nodes = [
        InfrastructureNodeEntity(
            id=r.id,
            node_name=r.node_name,
            infra_type=r.infra_type,
            criticality=r.criticality,
            failure_probability=r.failure_probability,
            location=GeoCoordinates(latitude=r.lat, longitude=r.lon),
            created_at=r.created_at,
        )
        for r in node_rows
    ]

    edges = [
        InfrastructureEdgeEntity(
            id=e.id,
            source_node_id=e.source_node_id,
            target_node_id=e.target_node_id,
            coupling_strength=e.coupling_strength,
            cascade_latency_seconds=e.cascade_latency_seconds,
            created_at=e.created_at,
        )
        for e in edge_rows
    ]

    _causal_engine.load_topology(nodes, edges)


@router.get("/nodes")
async def list_infra_nodes(
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists municipal and industrial infrastructure nodes in Istanbul DAG."""
    stmt = select(
        InfrastructureNodeOrm.id,
        InfrastructureNodeOrm.node_name,
        InfrastructureNodeOrm.infra_type,
        InfrastructureNodeOrm.criticality,
        InfrastructureNodeOrm.failure_probability,
        func.ST_X(InfrastructureNodeOrm.location).label("lon"),
        func.ST_Y(InfrastructureNodeOrm.location).label("lat"),
    )
    res = await session.execute(stmt)
    return [
        {
            "id": str(r.id),
            "node_name": r.node_name,
            "infra_type": r.infra_type,
            "criticality": r.criticality,
            "failure_probability": r.failure_probability,
            "location": {"latitude": r.lat, "longitude": r.lon},
        }
        for r in res.fetchall()
    ]


@router.post("/intervene")
async def simulate_intervention(
    req: InterveneRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Applies Pearl's do-operator do(X = x) and propagates downstream cascade failure probabilities."""
    await _load_engine_topology(session)
    post_probs = _causal_engine.do_intervention(req.node_id, req.fixed_state)
    loss = _causal_engine.compute_expected_system_loss(post_probs)

    return {
        "intervened_node_id": req.node_id,
        "fixed_state": req.fixed_state,
        "expected_system_loss": round(loss, 4),
        "node_probabilities": {k: round(v, 4) for k, v in post_probs.items()},
    }


@router.post("/countermeasures")
async def recommend_countermeasures(
    req: CountermeasureRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Runs submodular greedy optimization to select defensive node isolations under budget k."""
    await _load_engine_topology(session)
    recommendations = _causal_engine.submodular_greedy_countermeasures(req.root_node_id, req.budget_k)

    return {
        "root_incident_node_id": req.root_node_id,
        "budget_k": req.budget_k,
        "guarantee": "(1 - 1/e) ~ 63.2% optimal approximation bound",
        "countermeasures": [
            {
                "node_id": node_id,
                "node_name": name,
                "marginal_risk_reduction": round(reduction, 4),
            }
            for node_id, name, reduction in recommendations
        ],
    }
