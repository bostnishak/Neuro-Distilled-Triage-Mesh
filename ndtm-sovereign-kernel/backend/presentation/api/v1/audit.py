import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database.connection import get_db
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import MerkleAuditBlockOrm, KernelDomainEventOrm, UserOrm
from presentation.api.dependencies import get_current_user
from domain.services.merkle_audit_ledger import MerkleAuditLedger
from domain.services.time_travel_flight_recorder import TimeTravelFlightRecorder
from domain.events import DomainEvent

router = APIRouter(prefix="/audit", tags=["Cryptographic Merkle Ledger & Time-Travel"])
_flight_recorder = TimeTravelFlightRecorder()


class TimeTravelRequest(BaseModel):
    as_of_timestamp: str  # ISO-8601


@router.get("/blocks")
async def list_blocks(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists sealed Merkle audit chain blocks."""
    stmt = (
        select(MerkleAuditBlockOrm)
        .order_by(desc(MerkleAuditBlockOrm.height))
        .limit(limit)
    )
    res = await session.execute(stmt)
    rows = res.scalars().all()

    return [
        {
            "height": b.height,
            "block_hash": b.block_hash,
            "parent_hash": b.parent_hash,
            "merkle_root": b.merkle_root,
            "events_count": b.events_count,
            "sealed_at": b.sealed_at.isoformat(),
            "kernel_signature_hex": b.kernel_signature_hex,
        }
        for b in rows
    ]


@router.get("/verify")
async def verify_merkle_chain_integrity(
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Cryptographically verifies block hashes, parent links, and Ed25519 signatures from Genesis to tip."""
    stmt = select(MerkleAuditBlockOrm).order_by(MerkleAuditBlockOrm.height.asc())
    res = await session.execute(stmt)
    blocks = list(res.scalars().all())

    if not blocks:
        return {"status": "EMPTY_CHAIN", "verified": True, "block_count": 0}

    # Verify Genesis
    genesis = blocks[0]
    if genesis.height != 0:
        return {"status": "CORRUPTED", "error": "Genesis block (height 0) missing."}

    for i in range(1, len(blocks)):
        prev = blocks[i - 1]
        curr = blocks[i]

        try:
            MerkleAuditLedger.verify_chain_link(
                prev_block_hash=prev.block_hash,
                current_parent_hash=curr.parent_hash,
                current_block_hash=curr.block_hash,
                merkle_root=curr.merkle_root,
                height=curr.height,
                timestamp_iso=curr.sealed_at.isoformat(),
                events_count=curr.events_count,
                signature_hex=curr.kernel_signature_hex,
            )
        except Exception as e:
            return {
                "status": "TAMPER_DETECTED",
                "verified": False,
                "violated_at_height": curr.height,
                "error": str(e),
            }

    return {
        "status": "CHAIN_INTEGRITY_VERIFIED",
        "verified": True,
        "block_height_tip": blocks[-1].height,
        "total_blocks_verified": len(blocks),
    }


@router.post("/timetravel")
async def reconstruct_historical_state(
    req: TimeTravelRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Replays deterministic event sourced ledger and reconstructs historical world state as of timestamp."""
    try:
        as_of_dt = datetime.datetime.fromisoformat(req.as_of_timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ISO-8601 timestamp format.")

    stmt = select(KernelDomainEventOrm).order_by(KernelDomainEventOrm.occurred_at.asc())
    res = await session.execute(stmt)
    event_orms = res.scalars().all()

    # Convert to DomainEvent instances
    domain_events = [
        DomainEvent(
            event_id=ev.event_id,
            aggregate_type=ev.aggregate_type,
            aggregate_id=ev.aggregate_id,
            event_type=ev.event_type,
            version=ev.version,
            payload=ev.payload,
            occurred_at=ev.occurred_at,
            correlation_id=ev.correlation_id,
            signature_hex=ev.signature_hex,
        )
        for ev in event_orms
    ]

    snapshot = _flight_recorder.project_state_as_of(domain_events, as_of_dt)
    return snapshot
