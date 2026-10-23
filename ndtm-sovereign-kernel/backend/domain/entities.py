import datetime
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects import (
    GeoCoordinates,
    EmbeddingVector,
    MelSpectrogram,
    SmtProof,
    MerkleHash,
)


class UserEntity(BaseModel):
    """Immutable domain representation of an authenticated RBAC operator."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    email: str
    password_hash: str
    full_name: str
    role: str
    is_active: bool = True
    created_at: datetime.datetime


class IncidentEntity(BaseModel):
    """Immutable domain representation of an operational incident."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    cluster_id: Optional[uuid.UUID] = None
    title: str
    description_scrubbed: str
    raw_payload_encrypted: Optional[str] = None
    urgency: str
    category: str
    modality: str
    source_protocol: str
    location: GeoCoordinates
    address: Optional[str] = None
    embedding: Optional[EmbeddingVector] = None
    acoustic_signature: Optional[MelSpectrogram] = None
    optical_blur_score: Optional[float] = None
    triage_state: str
    triage_decision: Optional[str] = None
    triage_confidence: Optional[float] = None
    divergence_score: Optional[float] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime.datetime
    updated_at: datetime.datetime


class IncidentClusterEntity(BaseModel):
    """Hawkes spatio-temporal event cluster entity."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    root_incident_id: Optional[uuid.UUID] = None
    centroid: GeoCoordinates
    radius_meters: float
    cluster_urgency: str
    incident_count: int
    hawkes_mu: float
    hawkes_alpha: float
    hawkes_beta: float
    status: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class FieldTeamEntity(BaseModel):
    """Operational rapid response field unit."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    team_name: str
    specialization: str
    current_location: GeoCoordinates
    status: str
    shift_start_hour: int
    shift_end_hour: int
    burnout_index: float
    cumulative_shifts_week: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class DispatchScheduleEntity(BaseModel):
    """Z3 MaxSMT optimized deployment assignment."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    team_id: uuid.UUID
    dispatched_at: datetime.datetime
    estimated_arrival_minutes: float
    priority_weight: float
    smt_proof: Optional[SmtProof] = None
    is_active: bool = True
    completed_at: Optional[datetime.datetime] = None


class InfrastructureNodeEntity(BaseModel):
    """Critical municipal or industrial infrastructure dependency node."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    node_name: str
    infra_type: str
    location: GeoCoordinates
    criticality: float
    failure_probability: float
    created_at: datetime.datetime


class InfrastructureEdgeEntity(BaseModel):
    """Directed dependency link in infrastructure cascade DAG."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    source_node_id: uuid.UUID
    target_node_id: uuid.UUID
    coupling_strength: float
    cascade_latency_seconds: int
    created_at: datetime.datetime


class HitlApprovalEntity(BaseModel):
    """Human-in-the-Loop decision governance record."""
    model_config = ConfigDict(strict=True, frozen=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    proposed_action: str
    requires_role: str
    status: str
    justification_evidence: Dict[str, Any]
    arbiter_user_id: Optional[uuid.UUID] = None
    arbiter_signature_hex: Optional[str] = None
    decided_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime


class MerkleBlockEntity(BaseModel):
    """Cryptographically sealed audit chain block."""
    model_config = ConfigDict(strict=True, frozen=True)

    height: int
    block_hash: MerkleHash
    parent_hash: MerkleHash
    merkle_root: MerkleHash
    events_count: int
    sealed_at: datetime.datetime
    kernel_signature_hex: str
    state_commit_proof: Dict[str, Any] = Field(default_factory=dict)


class FederatedRoundEntity(BaseModel):
    """Byzantine-robust distributed active learning round."""
    model_config = ConfigDict(strict=True, frozen=True)

    round_number: int
    global_model_version: str
    status: str
    participating_nodes_count: int
    pruned_byzantine_nodes_count: int
    aggregated_gradient_norm: float
    renyi_epsilon_accumulated: float
    started_at: datetime.datetime
    completed_at: Optional[datetime.datetime] = None
