"""SQLAlchemy 2.0 declarative database models matching PostgreSQL 16 schema.
Includes Core V1 (Triage, Dispatch, Outbox, Telemetry) and V2 Frontier Expansion
(Causal Infrastructure Twin, MCP Tools, HITL, Federated Mesh, Merkle Audit Ledger).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.session import Base
from backend.schemas.auth import UserRole
from backend.schemas.router import ExecutionTarget
from backend.schemas.triage import TicketStatus


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.OPERATOR.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    incidents: Mapped[list["Incident"]] = relationship("Incident", back_populates="reporter")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    reporter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    parent_incident_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scrubbed_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    urgency_score: Mapped[int] = mapped_column(SmallInteger, CheckConstraint("urgency_score BETWEEN 1 AND 10"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TicketStatus.QUEUED.value, nullable=False, index=True)
    location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    image_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_laplacian_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    reporter: Mapped[User | None] = relationship("User", back_populates="incidents")
    schedules: Mapped[list["DispatchSchedule"]] = relationship("DispatchSchedule", back_populates="incident", cascade="all, delete-orphan")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    routing_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FieldTeam(Base):
    __tablename__ = "field_teams"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    team_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    shift_remaining_minutes: Mapped[int] = mapped_column(Integer, CheckConstraint("shift_remaining_minutes >= 0"), nullable=False)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    base_location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    schedules: Mapped[list["DispatchSchedule"]] = relationship("DispatchSchedule", back_populates="team")


class DispatchSchedule(Base):
    __tablename__ = "dispatch_schedules"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False)
    team_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("field_teams.id", ondelete="RESTRICT"), nullable=False)
    estimated_travel_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_work_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    z3_proof_smt2: Mapped[str] = mapped_column(Text, nullable=False)
    correction_iterations: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    incident: Mapped[Incident] = relationship("Incident", back_populates="schedules")
    team: Mapped[FieldTeam] = relationship("FieldTeam", back_populates="schedules")


class RouterTelemetryLog(Base):
    __tablename__ = "router_telemetry_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_target: Mapped[str] = mapped_column(String(32), nullable=False)
    student_entropy: Mapped[float | None] = mapped_column(Float, nullable=True)
    ood_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    cost_saved_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ShadowDriftSample(Base):
    __tablename__ = "shadow_drift_samples"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    student_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    teacher_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    kl_divergence: Mapped[float] = mapped_column(Float, nullable=False)
    used_for_retraining: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="IN_FLIGHT", nullable=False)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


# =============================================================================
# V2 FRONTIER EXPANSION MODELS
# =============================================================================

class InfrastructureNode(Base):
    __tablename__ = "infrastructure_nodes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    node_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    location: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)
    base_failure_prob: Mapped[float] = mapped_column(Float, default=0.01, nullable=False)
    current_health_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    capacity_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class InfrastructureEdge(Base):
    __tablename__ = "infrastructure_edges"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("infrastructure_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("infrastructure_nodes.id", ondelete="CASCADE"), nullable=False)
    dependency_weight: Mapped[float] = mapped_column(Float, nullable=False)
    propagation_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    coupling_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MCPToolInvocation(Base):
    __tablename__ = "mcp_tool_invocations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    jsonrpc_request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    jsonrpc_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    execution_ms: Mapped[float] = mapped_column(Float, nullable=False)
    sandbox_violation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class HITLApprovalRequest(Base):
    __tablename__ = "hitl_approval_requests"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    proposed_action_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    agent_consensus_score: Mapped[float] = mapped_column(Float, nullable=False)
    z3_proof_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING_HUMAN", nullable=False)
    approver_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ed25519_signature_hex: Mapped[str | None] = mapped_column(String(128), nullable=True)
    public_key_hex: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FederatedRound(Base):
    __tablename__ = "federated_rounds"

    round_number: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_weights_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregation_algorithm: Mapped[str] = mapped_column(String(32), default="MULTI_KRUM_DP", nullable=False)
    epsilon_spent: Mapped[float] = mapped_column(Float, nullable=False)
    delta_param: Mapped[float] = mapped_column(Float, nullable=False)
    participating_nodes: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_byzantine_nodes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FederatedNodeSubmission(Base):
    __tablename__ = "federated_node_submissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    round_number: Mapped[int] = mapped_column(Integer, ForeignKey("federated_rounds.round_number", ondelete="CASCADE"), nullable=False)
    edge_node_id: Mapped[str] = mapped_column(String(64), nullable=False)
    l2_norm_delta: Mapped[float] = mapped_column(Float, nullable=False)
    krum_distance_score: Mapped[float] = mapped_column(Float, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MerkleAuditLedger(Base):
    __tablename__ = "merkle_audit_ledger"

    seq_no: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, default=uuid4, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_block_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    block_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    merkle_root_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
