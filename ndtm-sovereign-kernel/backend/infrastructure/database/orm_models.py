import datetime
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from geoalchemy2 import Geometry


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class UserOrm(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )


class IncidentClusterOrm(Base):
    __tablename__ = "incident_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    root_incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    radius_meters: Mapped[float] = mapped_column(Float, default=500.0, nullable=False)
    cluster_urgency: Mapped[str] = mapped_column(String(50), default="MEDIUM", nullable=False)
    incident_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hawkes_mu: Mapped[float] = mapped_column(Float, default=0.01, nullable=False)
    hawkes_alpha: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    hawkes_beta: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )

    incidents: Mapped[List["IncidentOrm"]] = relationship(
        "IncidentOrm", back_populates="cluster", foreign_keys="IncidentOrm.cluster_id"
    )


class IncidentOrm(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_clusters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description_scrubbed: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    urgency: Mapped[str] = mapped_column(String(50), default="MEDIUM", nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    modality: Mapped[str] = mapped_column(String(50), default="TEXT_ONLY", nullable=False)
    source_protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding = Column(Vector(384), nullable=True)
    optical_blur_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triage_state: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False, index=True)
    triage_decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    triage_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    divergence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False, index=True
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )

    cluster: Mapped[Optional[IncidentClusterOrm]] = relationship(
        "IncidentClusterOrm", back_populates="incidents", foreign_keys=[cluster_id]
    )
    dispatches: Mapped[List["DispatchScheduleOrm"]] = relationship(
        "DispatchScheduleOrm", back_populates="incident"
    )
    hitl_requests: Mapped[List["HitlApprovalRequestOrm"]] = relationship(
        "HitlApprovalRequestOrm", back_populates="incident"
    )


class FieldTeamOrm(Base):
    __tablename__ = "field_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    specialization: Mapped[str] = mapped_column(String(50), nullable=False)
    current_location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="IDLE", nullable=False, index=True)
    shift_start_hour: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    shift_end_hour: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    burnout_index: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cumulative_shifts_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )

    dispatches: Mapped[List["DispatchScheduleOrm"]] = relationship(
        "DispatchScheduleOrm", back_populates="team"
    )


class DispatchScheduleOrm(Base):
    __tablename__ = "dispatch_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dispatched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    estimated_arrival_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    priority_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    smt_proof: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    incident: Mapped[IncidentOrm] = relationship("IncidentOrm", back_populates="dispatches")
    team: Mapped[FieldTeamOrm] = relationship("FieldTeamOrm", back_populates="dispatches")


class InfrastructureNodeOrm(Base):
    __tablename__ = "infrastructure_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    infra_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    criticality: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    failure_probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )


class InfrastructureEdgeOrm(Base):
    __tablename__ = "infrastructure_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("infrastructure_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("infrastructure_nodes.id", ondelete="CASCADE"), nullable=False
    )
    coupling_strength: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    cascade_latency_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )


class TransactionalOutboxOrm(Base):
    __tablename__ = "transactional_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    routing_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False, index=True
    )
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class KernelDomainEventOrm(Base):
    __tablename__ = "kernel_domain_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False, index=True
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    signature_hex: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class MerkleAuditBlockOrm(Base):
    __tablename__ = "merkle_audit_blocks"

    height: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    block_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    parent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    merkle_root: Mapped[str] = mapped_column(String(64), nullable=False)
    events_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sealed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    kernel_signature_hex: Mapped[str] = mapped_column(String(128), nullable=False)
    state_commit_proof: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class HitlApprovalRequestOrm(Base):
    __tablename__ = "hitl_approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proposed_action: Mapped[str] = mapped_column(String(100), nullable=False)
    requires_role: Mapped[str] = mapped_column(String(50), default="INCIDENT_COMMANDER", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    justification_evidence: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    arbiter_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    arbiter_signature_hex: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )

    incident: Mapped[IncidentOrm] = relationship("IncidentOrm", back_populates="hitl_requests")
    arbiter: Mapped[Optional[UserOrm]] = relationship("UserOrm")


class FederatedRoundOrm(Base):
    __tablename__ = "federated_rounds"

    round_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    global_model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PREPARING", nullable=False)
    participating_nodes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pruned_byzantine_nodes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    aggregated_gradient_norm: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    renyi_epsilon_accumulated: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    submissions: Mapped[List["FederatedNodeSubmissionOrm"]] = relationship(
        "FederatedNodeSubmissionOrm", back_populates="round"
    )


class FederatedNodeSubmissionOrm(Base):
    __tablename__ = "federated_node_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    round_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("federated_rounds.round_number", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_delta_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    l2_gradient_norm: Mapped[float] = mapped_column(Float, nullable=False)
    krum_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_byzantine_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )

    round: Mapped[FederatedRoundOrm] = relationship("FederatedRoundOrm", back_populates="submissions")


class TimeTravelSnapshotOrm(Base):
    __tablename__ = "time_travel_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_tag: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    as_of_block_height: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("merkle_audit_blocks.height"), nullable=False
    )
    state_payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False
    )
