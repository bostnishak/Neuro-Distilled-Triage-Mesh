export type UserRole = "OPERATOR" | "ARCHITECT" | "AUDITOR";

export type TicketStatus =
  | "REJECTED_QUALITY"
  | "DEDUPLICATED"
  | "QUEUED"
  | "TRIAGED"
  | "SCHEDULED"
  | "DLQ_FAILED";

export type ExecutionTarget =
  | "SEMANTIC_CACHE"
  | "ONNX_STUDENT_INT8"
  | "TEACHER_LLM_FALLBACK";

export interface IncidentSubmissionResponse {
  incident_id: string;
  status: TicketStatus;
  is_duplicate: boolean;
  parent_incident_id: string | null;
  duplicate_count: number;
  scrubbed_text: string;
  laplacian_score: number | null;
  distance_meters: number | null;
  cosine_similarity: number | null;
  message: string;
}

export interface RouterInferenceResponse {
  request_id: string;
  intent: string;
  confidence: number;
  urgency: number;
  execution_target: ExecutionTarget;
  student_entropy?: number;
  ood_similarity?: number;
  latency_ms: number;
  cost_saved_usd: number;
  from_cache: boolean;
}

export interface FieldTeamDTO {
  id: string;
  team_code: string;
  skills: string[];
  shift_remaining_minutes: number;
  max_concurrent_tasks: number;
  latitude: number;
  longitude: number;
  is_available: boolean;
}

export interface TaskAssignmentDTO {
  incident_id: string;
  team_id: string;
  estimated_travel_minutes: number;
  estimated_work_minutes: number;
  arrival_time_minutes: number;
}

export interface IterationAuditLog {
  iteration: number;
  status: "SAT" | "UNSAT";
  unsat_core_conflicts: string[];
  proposal: TaskAssignmentDTO[];
}

export interface Z3SolveResponse {
  is_sat: boolean;
  status: "VERIFIED" | "REPAIRED" | "Z3_OPTIMIZED" | "UNSAT_FATAL";
  assignments: TaskAssignmentDTO[];
  unsat_core_conflicts: string[];
  iteration_history: IterationAuditLog[];
  iterations_executed: number;
  z3_proof_smt2: string;
  solver_time_ms: number;
}

export interface LiveMetricsSnapshot {
  total_requests: number;
  onnx_offload_ratio: number;
  avg_latency_ms: number;
  cumulative_cost_saved_usd: number;
  circuit_breaker_state: "CLOSED" | "OPEN" | "HALF_OPEN";
  queue_depth_triage: number;
  queue_depth_shadow: number;
  queue_depth_dlq: number;
}

export interface ChaosResponse {
  scenario: string;
  action_taken: string;
  circuit_breaker_tripped: boolean;
  firewall_blocked: boolean;
  affected_subsystem: string;
  timestamp: number;
}

export interface DLQMessageItem {
  id: string;
  routing_key: string;
  payload: Record<string, any>;
  retry_count: number;
  error_reason: string;
  created_at: string;
}

// =============================================================================
// V2 FRONTIER EXPANSION INTERFACES
// =============================================================================

export interface InfraNodeDTO {
  id: string;
  node_code: string;
  node_type: string;
  latitude: number;
  longitude: number;
  base_failure_prob: number;
  current_health_score: number;
  capacity_kw?: number | null;
  metadata?: Record<string, any>;
}

export interface InfraEdgeDTO {
  source_code: string;
  target_code: string;
  dependency_weight: number;
  propagation_delay_minutes: number;
  coupling_type: string;
}

export interface TopologyResponse {
  nodes: InfraNodeDTO[];
  edges: InfraEdgeDTO[];
  total_nodes: number;
  total_edges: number;
}

export interface CascadeNodeImpact {
  node_code: string;
  failure_probability: number;
  time_to_fail_minutes: number;
  coupling_path: string[];
}

export interface CascadeSimulationResponse {
  root_failed_node: string;
  cascade_timeline: CascadeNodeImpact[];
  cumulative_risk_rating: number;
  affected_nodes_count: number;
}

export interface CounterfactualInterventionResponse {
  original_risk_rating: number;
  counterfactual_risk_rating: number;
  delta_crr: number;
  mutilated_edges_severed: string[];
  is_risk_mitigated: boolean;
}

export interface HITLApprovalItem {
  id: string;
  incident_id?: string | null;
  proposed_action: Record<string, any>;
  agent_consensus_score: number;
  z3_proof_hash: string;
  status: string;
  created_at: string;
}

export interface HITLSignResponse {
  id: string;
  status: string;
  signed_at: string;
  verified: boolean;
  message: string;
}

export interface FederatedStatusResponse {
  current_round: number;
  total_epsilon_spent: number;
  max_epsilon_budget: number;
  participating_nodes: string[];
  last_round_sha256: string;
}

export interface FederatedRoundExecuteResponse {
  round_number: number;
  participating_nodes_count: number;
  rejected_byzantine_count: number;
  rejected_node_ids: string[];
  epsilon_spent: number;
  global_weights_sha256: string;
  algorithm: string;
}

export interface MerkleBlockItem {
  seq_no: number;
  event_id: string;
  event_type: string;
  actor_id: string;
  canonical_payload: Record<string, any>;
  payload_sha256: string;
  prev_block_hash: string;
  block_hash: string;
  merkle_root_snapshot: string;
  created_at: string;
}

export interface MerkleVerifyResponse {
  valid: boolean;
  total_blocks_verified: number;
  merkle_root: string;
  tampered_seq_no: number | null;
  reason: string | null;
}

export interface SpeculativeDecodeResponse {
  generated_text: string;
  acceptance_rate: number;
  draft_tokens_proposed: number;
  tokens_accepted: number;
  speedup_ratio: number;
  resampled_count: number;
}

export interface LoRASwapResponse {
  previous_adapter: string;
  active_adapter: string;
  adapter_checksum_sha256: string;
  swapped_at: string;
}
