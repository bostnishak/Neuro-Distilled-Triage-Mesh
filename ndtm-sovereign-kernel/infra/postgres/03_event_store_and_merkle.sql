-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — EVENT SOURCING, TIME-TRAVEL & MERKLE LEDGER
-- Phase 1: Immutable Flight Recorder, HITL Asymmetric Gates & Byzantine Rounds
-- ==============================================================================

-- 1. Immutable Event-Sourced Kernel Domain Events
CREATE TABLE IF NOT EXISTS kernel_domain_events (
    seq_no BIGSERIAL PRIMARY KEY,
    event_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    timestamp_ns BIGINT NOT NULL,
    universe_branch_id VARCHAR(64) NOT NULL DEFAULT 'MAIN_TIMELINE',
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload_json JSONB NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    block_hash VARCHAR(64) NOT NULL,
    merkle_root VARCHAR(64) NOT NULL,
    signature_ed25519 VARCHAR(128) DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_branch_seq 
ON kernel_domain_events (universe_branch_id, seq_no ASC);

CREATE INDEX IF NOT EXISTS idx_events_aggregate 
ON kernel_domain_events (aggregate_type, aggregate_id);

CREATE INDEX IF NOT EXISTS idx_events_type 
ON kernel_domain_events (event_type);

-- 2. Cryptographic Merkle Audit Blocks
CREATE TABLE IF NOT EXISTS merkle_audit_blocks (
    block_height BIGINT PRIMARY KEY,
    start_seq_no BIGINT NOT NULL,
    end_seq_no BIGINT NOT NULL,
    event_count INT NOT NULL,
    merkle_root VARCHAR(64) NOT NULL,
    prev_block_hash VARCHAR(64) NOT NULL,
    block_hash VARCHAR(64) NOT NULL,
    sealed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validator_signature VARCHAR(128) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_merkle_block_height 
ON merkle_audit_blocks (block_height DESC);

-- 3. Human-In-The-Loop (HITL) Asymmetric Cryptographic Approval Gate
CREATE TABLE IF NOT EXISTS hitl_approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    proposed_action JSONB NOT NULL,
    agent_consensus_score FLOAT8 NOT NULL,
    z3_proof_hash VARCHAR(64) NOT NULL,
    status hitl_approval_status_enum NOT NULL DEFAULT 'PENDING_HUMAN',
    approver_email VARCHAR(255) DEFAULT NULL,
    public_key_hex VARCHAR(64) DEFAULT NULL,
    ed25519_signature_hex VARCHAR(128) DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_hitl_status 
ON hitl_approval_requests (status) 
WHERE status = 'PENDING_HUMAN';

CREATE INDEX IF NOT EXISTS idx_hitl_incident 
ON hitl_approval_requests (incident_id);

-- 4. Byzantine-Resilient Federated Rounds & Privacy Accounting
CREATE TABLE IF NOT EXISTS federated_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_num INT UNIQUE NOT NULL,
    global_model_version VARCHAR(64) NOT NULL,
    epsilon_spent FLOAT8 NOT NULL,
    delta_budget FLOAT8 NOT NULL,
    byzantine_nodes_isolated TEXT[] NOT NULL DEFAULT '{}',
    aggregated_weights_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fed_round_num 
ON federated_rounds (round_num DESC);

-- 5. Individual Edge Node Gradient Submissions
CREATE TABLE IF NOT EXISTS federated_node_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES federated_rounds(id) ON DELETE CASCADE,
    node_id VARCHAR(64) NOT NULL,
    l2_clipped_norm FLOAT8 NOT NULL,
    krum_distance_score FLOAT8 NOT NULL,
    is_byzantine_flagged BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fed_submissions_round 
ON federated_node_submissions (round_id);

-- 6. Event-Sourced Time-Travel Snapshots (Historical Branch Checkpoints)
CREATE TABLE IF NOT EXISTS time_travel_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_branch_id VARCHAR(64) NOT NULL,
    at_seq_no BIGINT NOT NULL,
    parent_branch_id VARCHAR(64) DEFAULT NULL,
    mutation_description TEXT DEFAULT NULL,
    state_snapshot_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_time_travel_branch_seq 
ON time_travel_snapshots (universe_branch_id, at_seq_no);

-- 7. Anti-Tamper Immutability Triggers (Reject Any UPDATE or DELETE)
CREATE OR REPLACE FUNCTION prevent_event_store_tampering()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'CRITICAL SECURITY VIOLATION: % is an append-only cryptographic ledger. Updates and deletions are strictly prohibited.', TG_TABLE_NAME
        USING ERRCODE = '23505';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_tamper_kernel_events ON kernel_domain_events;
CREATE TRIGGER trg_prevent_tamper_kernel_events
BEFORE UPDATE OR DELETE ON kernel_domain_events
FOR EACH ROW EXECUTE FUNCTION prevent_event_store_tampering();

DROP TRIGGER IF EXISTS trg_prevent_tamper_merkle_blocks ON merkle_audit_blocks;
CREATE TRIGGER trg_prevent_tamper_merkle_blocks
BEFORE UPDATE OR DELETE ON merkle_audit_blocks
FOR EACH ROW EXECUTE FUNCTION prevent_event_store_tampering();
