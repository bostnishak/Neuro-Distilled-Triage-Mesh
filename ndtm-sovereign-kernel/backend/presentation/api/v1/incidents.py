import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import numpy as np

from infrastructure.database.connection import get_db
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import IncidentOrm, IncidentClusterOrm, UserOrm
from presentation.api.dependencies import get_current_user
from application.middleware.pii_scrubber import PIIScrubber
from application.middleware.owasp_llm_firewall import OWASPLLMFirewall
from application.middleware.gcra_rate_limiter import GCRARateLimiter
from domain.services.onnx_runtime_engine import OnnxRuntimeEngine
from domain.services.pid_entropy_router import ModelRouter
from domain.services.text_encoder import encode_text_to_feature_vector
from domain.events import IncidentIngestedEvent

router = APIRouter(prefix="/incidents", tags=["Incidents Ingestion & Triage"])

_gcra_limiter = GCRARateLimiter()
_onnx_engine = OnnxRuntimeEngine()
_router_engine = ModelRouter()


class IngestIncidentRequest(BaseModel):
    title: str = Field(..., max_length=255)
    description: str
    urgency: str = Field(default="MEDIUM", pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$")
    category: Optional[str] = None
    modality: str = Field(default="TEXT_ONLY", pattern="^(TEXT_ONLY|TEXT_OPTICAL|ACOUSTIC_ONLY|MULTIMODAL)$")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    address: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class SemanticSearchRequest(BaseModel):
    query_text: str
    top_k: int = Field(default=5, ge=1, le=50)


class SpatialSearchRequest(BaseModel):
    latitude: float
    longitude: float
    radius_meters: float = Field(default=1000.0, ge=10.0, le=50000.0)
    time_window_hours: int = Field(default=6, ge=1, le=168)


@router.post("", status_code=status.HTTP_201_CREATED)
async def ingest_incident(
    req: IngestIncidentRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Ingests raw operational report, applies security filters, computes AI inference and records event."""
    # 1. GCRA Rate Limiting
    await _gcra_limiter.check_rate_limit(f"user:{current_user.id}")

    # 2. PII Scrubbing
    scrubbed_desc, redactions = PIIScrubber.scrub_text(req.description)

    # 3. OWASP LLM Firewall
    is_threat, threat_reasons = OWASPLLMFirewall.inspect(scrubbed_desc)
    assigned_urgency = "CRITICAL" if is_threat else req.urgency

    # 4. Model Inference & Semantic Feature Encoding
    feature_vec = encode_text_to_feature_vector(scrubbed_desc, dim=384)
    pred_cat, conf, probs, embedding = _onnx_engine.infer_triage(feature_vec)

    # Use client category if explicitly provided, else model prediction
    final_category = req.category or pred_cat

    # 5. Route Decision
    route_decision, entropy, ood_dist, dyn_thresh = _router_engine.evaluate_route(
        probs, embedding, assigned_urgency
    )

    # 6. Database Transaction & Event Sourcing
    async with UnitOfWork(session) as uow:
        # Spatial cluster match
        matched_cluster = await uow.clusters.find_matching_cluster(req.longitude, req.latitude)
        cluster_id = None
        if matched_cluster:
            cluster_id = matched_cluster.id
            matched_cluster.incident_count += 1
        else:
            new_cid = uuid.uuid4()
            cluster_orm = IncidentClusterOrm(
                id=new_cid,
                centroid=f"SRID=4326;POINT({req.longitude:.7f} {req.latitude:.7f})",
                radius_meters=500.0,
                cluster_urgency=assigned_urgency,
                incident_count=1,
            )
            await uow.clusters.create(cluster_orm)
            cluster_id = new_cid

        inc_id = uuid.uuid4()
        inc_orm = IncidentOrm(
            id=inc_id,
            cluster_id=cluster_id,
            title=req.title,
            description_scrubbed=scrubbed_desc,
            urgency=assigned_urgency,
            category=final_category,
            modality=req.modality,
            source_protocol="REST_API",
            location=f"SRID=4326;POINT({req.longitude:.7f} {req.latitude:.7f})",
            address=req.address or "Istanbul Metro Zone",
            embedding=embedding.tolist(),
            triage_state="PENDING_HITL" if route_decision == "HITL_REQUIRED" else "TRIAGED",
            triage_decision=final_category,
            triage_confidence=conf,
            metadata_json={
                "entropy": entropy,
                "ood_dist": ood_dist,
                "route_decision": route_decision,
                "redactions_count": redactions,
                "threat_flag": is_threat,
                "extra": req.metadata_json,
            },
        )
        await uow.incidents.create(inc_orm)

        # Domain event
        ev = IncidentIngestedEvent(
            aggregate_type="Incident",
            aggregate_id=inc_id,
            event_type="IncidentIngested",
            payload={
                "incident_id": str(inc_id),
                "category": final_category,
                "urgency": assigned_urgency,
                "confidence": conf,
                "route": route_decision,
            },
        ).sign()

        await uow.outbox.enqueue(
            aggregate_type="Incident",
            aggregate_id=inc_id,
            event_type="IncidentIngested",
            payload=ev.payload,
            routing_key=f"incident.ingested.{assigned_urgency.lower()}",
        )

    return {
        "id": str(inc_id),
        "cluster_id": str(cluster_id) if cluster_id else None,
        "title": req.title,
        "category": final_category,
        "urgency": assigned_urgency,
        "triage_state": inc_orm.triage_state,
        "confidence": conf,
        "route_decision": route_decision,
        "entropy": entropy,
        "redactions": redactions,
    }


@router.get("")
async def list_incidents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Lists active operational incidents."""
    async with UnitOfWork(session) as uow:
        incidents = await uow.incidents.list_active(limit=limit, offset=offset)
        return [
            {
                "id": str(i.id),
                "cluster_id": str(i.cluster_id) if i.cluster_id else None,
                "title": i.title,
                "description": i.description_scrubbed,
                "category": i.category,
                "urgency": i.urgency,
                "triage_state": i.triage_state,
                "confidence": i.triage_confidence,
                "created_at": i.created_at.isoformat(),
            }
            for i in incidents
        ]


@router.post("/search/semantic")
async def search_semantic(
    req: SemanticSearchRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Performs semantic similarity search over incident vectors via pgvector HNSW."""
    # Generate embedding for query text via unit-normalized n-gram projection
    query_emb = encode_text_to_feature_vector(req.query_text, dim=384)

    async with UnitOfWork(session) as uow:
        results = await uow.incidents.find_semantic_neighbors(query_emb.tolist(), top_k=req.top_k)
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "category": r.category,
                "urgency": r.urgency,
                "triage_state": r.triage_state,
            }
            for r in results
        ]


@router.post("/search/spatial")
async def search_spatial(
    req: SpatialSearchRequest,
    current_user: UserOrm = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Finds incidents within spatial radius and time window using PostGIS ST_DWithin."""
    async with UnitOfWork(session) as uow:
        results = await uow.incidents.find_spatial_neighbors(
            longitude=req.longitude,
            latitude=req.latitude,
            radius_meters=req.radius_meters,
            time_window_hours=req.time_window_hours,
        )
        return [
            {
                "id": str(r.id),
                "title": r.title,
                "category": r.category,
                "urgency": r.urgency,
                "created_at": r.created_at.isoformat(),
            }
            for r in results
        ]
