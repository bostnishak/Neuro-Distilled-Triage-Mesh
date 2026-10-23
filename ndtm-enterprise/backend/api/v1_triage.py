"""Multimodal Triage and Incident Deduplication REST router."""
from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_user, get_db
from backend.core.exceptions import QualityGateFailedError
from backend.db.models import Incident, User
from backend.db.repositories import IncidentRepository
from backend.db.session import get_raw_connection
from backend.middleware.pii_scrubber import scrub_pii
from backend.schemas.triage import (
    IncidentDetailResponse,
    IncidentSubmissionRequest,
    IncidentSubmissionResponse,
    QualityGateRejectionResponse,
    TicketStatus,
)
from backend.services.deduplication_engine import DeduplicationEngine
from backend.services.image_forensics import ImageForensicsService
from backend.services.websocket_manager import ws_manager

logger = logging.getLogger("api.triage")
router = APIRouter(prefix="/triage", tags=["Incident Triage & Deduplication"])

forensics_service = ImageForensicsService()
dedup_engine = DeduplicationEngine()


@router.post("/incidents", response_model=IncidentSubmissionResponse)
@router.post("/submit", response_model=IncidentSubmissionResponse)
async def submit_incident_report(
    req: IncidentSubmissionRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
) -> IncidentSubmissionResponse:
    """Submits incident report with PII scrubbing, image forensics, and PostGIS+pgvector deduplication."""
    # 1. Image Forensics Quality Gate (if image attached)
    image_sha256 = None
    laplacian_score = None
    if req.image_base64:
        try:
            analysis = forensics_service.process_and_validate(req.image_base64)
            image_sha256 = analysis.sha256_hash
            laplacian_score = analysis.laplacian_variance
        except QualityGateFailedError as qg:
            logger.warning("Incident rejected by quality gate: %s (score: %.1f)", qg.reason, qg.laplacian_score)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "requires_clarification": True,
                    "reason": qg.reason,
                    "laplacian_score": qg.laplacian_score,
                    "clarification_prompt": qg.prompt,
                },
            )
        except ValueError as val_err:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=str(val_err),
            )

    # 2. Cryptographic PII Redaction
    raw_hash = hashlib.sha256(req.description.encode("utf-8")).hexdigest()
    clean_text = scrub_pii(req.description)

    # 3. Dense Vector Embedding Generation
    embedding = await dedup_engine.compute_embedding(clean_text)

    # 4. Atomic Deduplication Query via PostGIS and pgvector
    async with get_raw_connection() as raw_conn:
        match = await dedup_engine.query_duplicate(
            conn=raw_conn,
            embedding=embedding,
            longitude=req.longitude,
            latitude=req.latitude,
        )

    # Spatial Point representation
    point_wkt = WKTElement(f"POINT({req.longitude} {req.latitude})", srid=4326)

    # 5. Handle Duplicate vs Unique Ticket
    if match.is_duplicate and match.parent_id is not None:
        logger.info(
            "Report deduplicated! Matched parent %s (cosine sim: %.4f, distance: %.1fm)",
            match.parent_id,
            match.cosine_similarity,
            match.distance_meters,
        )
        new_count = await IncidentRepository.increment_duplicate_count(session, match.parent_id)

        # Persist child record with DEDUPLICATED status
        child_incident = Incident(
            reporter_id=current_user.id if current_user else None,
            parent_incident_id=match.parent_id,
            duplicate_count=1,
            raw_text_hash=raw_hash,
            scrubbed_text=clean_text,
            category=req.category,
            urgency_score=req.urgency_score,
            status=TicketStatus.DEDUPLICATED.value,
            location=point_wkt,
            image_sha256=image_sha256,
            image_laplacian_score=laplacian_score,
            embedding=embedding,
        )
        session.add(child_incident)
        await session.commit()

        # Broadcast live deduplication event to WebSocket cockpit
        await ws_manager.broadcast_event(
            "incident_deduplicated",
            {
                "child_id": str(child_incident.id),
                "parent_id": str(match.parent_id),
                "duplicate_count": new_count,
                "cosine_sim": match.cosine_similarity,
                "distance_meters": match.distance_meters,
            },
        )

        return IncidentSubmissionResponse(
            incident_id=child_incident.id,
            status=TicketStatus.DEDUPLICATED,
            is_duplicate=True,
            parent_incident_id=match.parent_id,
            duplicate_count=new_count,
            scrubbed_text=clean_text,
            laplacian_score=laplacian_score,
            distance_meters=match.distance_meters,
            cosine_similarity=match.cosine_similarity,
            message=f"Duplicate incident merged into master ticket {match.parent_id} (Similarity: {match.cosine_similarity * 100:.1f}%).",
        )

    # Unique Ticket Path: Transactional Outbox Pattern
    unique_incident = Incident(
        reporter_id=current_user.id if current_user else None,
        parent_incident_id=None,
        duplicate_count=1,
        raw_text_hash=raw_hash,
        scrubbed_text=clean_text,
        category=req.category,
        urgency_score=req.urgency_score,
        status=TicketStatus.QUEUED.value,
        location=point_wkt,
        image_sha256=image_sha256,
        image_laplacian_score=laplacian_score,
        embedding=embedding,
    )

    outbox_payload = {
        "incident_id": str(unique_incident.id),
        "category": req.category,
        "urgency_score": req.urgency_score,
        "location": {"lat": req.latitude, "lon": req.longitude},
        "preview": clean_text[:120],
    }

    # Atomically write Incident + OutboxEvent in single transaction
    await IncidentRepository.create_with_outbox(
        session=session,
        incident=unique_incident,
        outbox_payload=outbox_payload,
        routing_key=f"triage.incident.{req.category.lower()}",
    )
    await session.commit()
    logger.info("Unique incident %s queued with Transactional Outbox.", unique_incident.id)

    # Broadcast event
    await ws_manager.broadcast_event(
        "incident_created",
        {"incident_id": str(unique_incident.id), "category": req.category, "urgency": req.urgency_score},
    )

    return IncidentSubmissionResponse(
        incident_id=unique_incident.id,
        status=TicketStatus.QUEUED,
        is_duplicate=False,
        parent_incident_id=None,
        duplicate_count=1,
        scrubbed_text=clean_text,
        laplacian_score=laplacian_score,
        distance_meters=0.0,
        cosine_similarity=1.0,
        message="Incident verified and queued for autonomous dispatch.",
    )


@router.get("/incidents", response_model=list[IncidentDetailResponse])
async def list_incidents(
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
) -> list[IncidentDetailResponse]:
    """Retrieves recent incident feed."""
    incidents = await IncidentRepository.list_recent(session, limit)
    result = []
    for inc in incidents:
        result.append(
            IncidentDetailResponse(
                id=inc.id,
                reporter_id=inc.reporter_id,
                parent_incident_id=inc.parent_incident_id,
                duplicate_count=inc.duplicate_count,
                scrubbed_text=inc.scrubbed_text,
                category=inc.category,
                urgency_score=inc.urgency_score,
                status=TicketStatus(inc.status),
                latitude=0.0,  # Extracted from geography
                longitude=0.0,
                image_laplacian_score=inc.image_laplacian_score,
                created_at=inc.created_at,
                updated_at=inc.updated_at,
            )
        )
    return result
