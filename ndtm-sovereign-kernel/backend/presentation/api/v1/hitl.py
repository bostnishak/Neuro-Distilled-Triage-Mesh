import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_db
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import HitlApprovalRequestOrm, UserOrm
from presentation.api.dependencies import get_current_user, require_role
from application.hitl_arbiter import HitlArbiterService

router = APIRouter(prefix="/hitl", tags=["Human-in-the-Loop Governance"])
_hitl_service = HitlArbiterService()


class HitlDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")
    signature_hex: str = Field(..., min_length=128, max_length=128)
    public_key_hex: Optional[str] = None


@router.get("/pending")
async def list_pending_requests(
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists unresolved HITL arbitration requests awaiting human approval."""
    stmt = (
        select(HitlApprovalRequestOrm)
        .where(HitlApprovalRequestOrm.status == "PENDING")
        .order_by(HitlApprovalRequestOrm.created_at.desc())
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    return [
        {
            "id": str(r.id),
            "incident_id": str(r.incident_id),
            "proposed_action": r.proposed_action,
            "requires_role": r.requires_role,
            "justification": r.justification_evidence,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/{request_id}/decision")
async def submit_arbiter_decision(
    request_id: uuid.UUID,
    req: HitlDecisionRequest,
    current_user: UserOrm = Depends(require_role("INCIDENT_COMMANDER")),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Commits cryptographic decision signed with arbiter's Ed25519 private key."""
    async with UnitOfWork(session) as uow:
        res = await _hitl_service.submit_decision(
            uow=uow,
            request_id=request_id,
            arbiter_user_id=current_user.id,
            arbiter_role=current_user.role,
            decision=req.decision,
            arbiter_signature_hex=req.signature_hex,
            arbiter_public_key_hex=req.public_key_hex,
        )
        return {
            "status": "DECISION_COMMITTED",
            "request_id": str(res.id),
            "decision": res.status,
            "decided_at": res.decided_at.isoformat() if res.decided_at else None,
        }
