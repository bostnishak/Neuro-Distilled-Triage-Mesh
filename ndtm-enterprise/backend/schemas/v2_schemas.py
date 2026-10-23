"""Pydantic v2 data transfer schemas for NDTM v2.0 Frontier Expansion modules.
Covers Causal Digital Twin, MCP Protocol, HITL Cryptographic Gates,
Federated Mesh Learning, and Speculative Decoding / Merkle Ledger.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# 1. Causal Digital Twin Schemas
# -----------------------------------------------------------------------------
class NodeTypeEnum(str, Enum):
    SUBSTATION = "SUBSTATION"
    FIBER_BACKBONE = "FIBER_BACKBONE"
    CELL_TOWER = "CELL_TOWER"
    WATER_PUMP = "WATER_PUMP"
    FACTORY_FURNACE = "FACTORY_FURNACE"


class CouplingTypeEnum(str, Enum):
    POWER_FEED = "POWER_FEED"
    TELECOM_BACKHAUL = "TELECOM_BACKHAUL"
    COOLING_SUPPLY = "COOLING_SUPPLY"


class InfraNodeDTO(BaseModel):
    id: str
    node_code: str
    node_type: NodeTypeEnum
    latitude: float
    longitude: float
    base_failure_prob: float
    current_health_score: float
    capacity_kw: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InfraEdgeDTO(BaseModel):
    source_code: str
    target_code: str
    dependency_weight: float
    propagation_delay_minutes: int
    coupling_type: CouplingTypeEnum


class TopologyResponse(BaseModel):
    nodes: list[InfraNodeDTO]
    edges: list[InfraEdgeDTO]
    total_nodes: int
    total_edges: int


class CascadeSimulationRequest(BaseModel):
    failed_node_code: str = Field(..., description="Node code where initial failure occurs")
    time_horizon_minutes: int = Field(default=60, ge=1, le=240)


class CascadeNodeImpact(BaseModel):
    node_code: str
    failure_probability: float
    time_to_fail_minutes: int
    coupling_path: list[str]


class CascadeSimulationResponse(BaseModel):
    root_failed_node: str
    cascade_timeline: list[CascadeNodeImpact]
    cumulative_risk_rating: float
    affected_nodes_count: int


class CounterfactualInterventionRequest(BaseModel):
    failed_node_code: str
    intervened_node_code: str
    intervention_action: str = Field(default="REINFORCED", description="Structural intervention applied to node")


class CounterfactualInterventionResponse(BaseModel):
    original_risk_rating: float
    counterfactual_risk_rating: float
    delta_crr: float
    mutilated_edges_severed: list[str]
    is_risk_mitigated: bool


# -----------------------------------------------------------------------------
# 2. MCP JSON-RPC & Byzantine HITL Consensus Schemas
# -----------------------------------------------------------------------------
class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: str | int


class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Any | None = None
    error: dict[str, Any] | None = None
    id: str | int


class HITLApprovalItem(BaseModel):
    id: str
    incident_id: str | None = None
    proposed_action: dict[str, Any]
    agent_consensus_score: float
    z3_proof_hash: str
    status: str
    created_at: str


class HITLSignRequest(BaseModel):
    approver_email: str
    public_key_hex: str = Field(..., min_length=64, max_length=64)
    ed25519_signature_hex: str = Field(..., min_length=128, max_length=128)


class HITLSignResponse(BaseModel):
    id: str
    status: str
    signed_at: str
    verified: bool
    message: str


# -----------------------------------------------------------------------------
# 3. Byzantine Federated Learning & DP Schemas
# -----------------------------------------------------------------------------
class GradientSubmissionRequest(BaseModel):
    edge_node_id: str
    round_number: int
    gradient_vector: list[float] = Field(..., description="Local model gradient delta")


class GradientSubmissionResponse(BaseModel):
    accepted: bool
    l2_norm: float
    message: str


class FederatedRoundExecuteResponse(BaseModel):
    round_number: int
    participating_nodes_count: int
    rejected_byzantine_count: int
    rejected_node_ids: list[str]
    epsilon_spent: float
    global_weights_sha256: str
    algorithm: str


class FederatedStatusResponse(BaseModel):
    current_round: int
    total_epsilon_spent: float
    max_epsilon_budget: float
    participating_nodes: list[str]
    last_round_sha256: str


# -----------------------------------------------------------------------------
# 4. Speculative Decoding & LoRA Hot-Swapper Schemas
# -----------------------------------------------------------------------------
class SpeculativeDecodeRequest(BaseModel):
    prompt: str
    max_tokens: int = Field(default=32, ge=4, le=128)
    draft_lookahead_k: int = Field(default=4, ge=1, le=8)


class SpeculativeDecodeResponse(BaseModel):
    generated_text: str
    acceptance_rate: float
    draft_tokens_proposed: int
    tokens_accepted: int
    speedup_ratio: float
    resampled_count: int


class LoRASwapRequest(BaseModel):
    adapter_name: str = Field(..., description="LoRA adapter identifier (e.g. TELECOM_FIBER, ENERGY_GRID)")


class LoRASwapResponse(BaseModel):
    previous_adapter: str
    active_adapter: str
    adapter_checksum_sha256: str
    swapped_at: str


class ActiveAdaptersResponse(BaseModel):
    active_adapter: str
    available_adapters: list[str]


# -----------------------------------------------------------------------------
# 5. Merkle Audit Ledger Schemas
# -----------------------------------------------------------------------------
class MerkleBlockItem(BaseModel):
    seq_no: int
    event_id: str
    event_type: str
    actor_id: str
    canonical_payload: dict[str, Any]
    payload_sha256: str
    prev_block_hash: str
    block_hash: str
    merkle_root_snapshot: str
    created_at: str


class MerkleVerifyResponse(BaseModel):
    valid: bool
    total_blocks_verified: int
    merkle_root: str
    tampered_seq_no: int | None = None
    reason: str | None = None
