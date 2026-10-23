"""Byzantine-Resilient Federated Learning & Differential Privacy API Router (NDTM v2.0)."""
from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, status

from backend.federated_mesh.dp_gaussian_accountant import PrivacyBudgetExhaustedError
from backend.federated_mesh.edge_sync_coordinator import federated_coordinator
from backend.schemas.v2_schemas import (
    FederatedRoundExecuteResponse,
    FederatedStatusResponse,
    GradientSubmissionRequest,
    GradientSubmissionResponse,
)

logger = logging.getLogger("api.federated")
router = APIRouter(prefix="/federated", tags=["Federated Mesh & Privacy"])


@router.get("/status", response_model=FederatedStatusResponse)
async def get_federated_mesh_status() -> FederatedStatusResponse:
    """Returns current active federated round status, participating edge nodes, and cumulative DP epsilon spent."""
    st = federated_coordinator.get_status()
    return FederatedStatusResponse(
        current_round=st["current_round"],
        total_epsilon_spent=st["total_epsilon_spent"],
        max_epsilon_budget=st["max_epsilon_budget"],
        participating_nodes=st["participating_nodes"],
        last_round_sha256=st["last_round_sha256"],
    )


@router.post("/submit", response_model=GradientSubmissionResponse)
async def submit_edge_gradient(
    req: GradientSubmissionRequest,
) -> GradientSubmissionResponse:
    """Ingests edge node gradient delta, applying L2 norm clipping."""
    accepted, norm = federated_coordinator.submit_gradient(
        edge_node_id=req.edge_node_id,
        round_no=req.round_number,
        gradient=req.gradient_vector,
    )
    return GradientSubmissionResponse(
        accepted=accepted,
        l2_norm=norm,
        message=f"Gradient submission received. L2 norm: {norm:.4f}.",
    )


@router.post("/round/execute", response_model=FederatedRoundExecuteResponse)
async def execute_federated_aggregation_round() -> FederatedRoundExecuteResponse:
    """Executes Multi-Krum Byzantine filtering, spends DP budget, and applies Gaussian perturbation."""
    try:
        res = federated_coordinator.execute_round()
        return FederatedRoundExecuteResponse(
            round_number=res["round_number"],
            participating_nodes_count=res["participating_nodes_count"],
            rejected_byzantine_count=res["rejected_byzantine_count"],
            rejected_node_ids=res["rejected_node_ids"],
            epsilon_spent=res["epsilon_spent"],
            global_weights_sha256=res["global_weights_sha256"],
            algorithm=res["algorithm"],
        )
    except PrivacyBudgetExhaustedError as pbe:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(pbe),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Aggregation error: {exc}",
        )
