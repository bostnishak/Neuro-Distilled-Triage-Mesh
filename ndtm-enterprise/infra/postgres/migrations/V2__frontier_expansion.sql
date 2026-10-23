-- =============================================================================
-- Migration V2: Frontier Expansion Schema (NDTM v2.0 Sovereign Edition)
-- Modules: Causal Digital Twin, Model Context Protocol (MCP), HITL Crypto Gates,
--          Federated Privacy Mesh, and Cryptographic Merkle Audit Ledger.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- -----------------------------------------------------------------------------
-- 1. CAUSAL DIGITAL TWIN TOPOLOGY (Nodes & Dependency Edges)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infrastructure_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_code VARCHAR(64) UNIQUE NOT NULL,
    node_type VARCHAR(32) NOT NULL CHECK (
        node_type IN ('SUBSTATION', 'FIBER_BACKBONE', 'CELL_TOWER', 'WATER_PUMP', 'FACTORY_FURNACE')
    ),
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    base_failure_prob DOUBLE PRECISION NOT NULL DEFAULT 0.01 CHECK (base_failure_prob BETWEEN 0.0 AND 1.0),
    current_health_score DOUBLE PRECISION NOT NULL DEFAULT 100.0 CHECK (current_health_score BETWEEN 0.0 AND 100.0),
    capacity_kw DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_infra_nodes_location ON infrastructure_nodes USING GIST(location);
CREATE INDEX IF NOT EXISTS idx_infra_nodes_type ON infrastructure_nodes(node_type);

CREATE TABLE IF NOT EXISTS infrastructure_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_node_id UUID NOT NULL REFERENCES infrastructure_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES infrastructure_nodes(id) ON DELETE CASCADE,
    dependency_weight DOUBLE PRECISION NOT NULL CHECK (dependency_weight BETWEEN 0.0 AND 1.0),
    propagation_delay_minutes INT NOT NULL CHECK (propagation_delay_minutes >= 0),
    coupling_type VARCHAR(32) NOT NULL CHECK (
        coupling_type IN ('POWER_FEED', 'TELECOM_BACKHAUL', 'COOLING_SUPPLY')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_infra_edge_pair UNIQUE(source_node_id, target_node_id),
    CONSTRAINT chk_no_self_loop CHECK (source_node_id <> target_node_id)
);

CREATE INDEX IF NOT EXISTS idx_infra_edges_source ON infrastructure_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_infra_edges_target ON infrastructure_edges(target_node_id);

-- -----------------------------------------------------------------------------
-- 2. MODEL CONTEXT PROTOCOL (MCP) & CRYPTOGRAPHIC HITL
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mcp_tool_invocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL,
    agent_role VARCHAR(64) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    jsonrpc_request JSONB NOT NULL,
    jsonrpc_response JSONB NOT NULL,
    execution_ms DOUBLE PRECISION NOT NULL,
    sandbox_violation BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mcp_session ON mcp_tool_invocations(session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tool_name ON mcp_tool_invocations(tool_name);
CREATE INDEX IF NOT EXISTS idx_mcp_created_at ON mcp_tool_invocations(created_at);

CREATE TABLE IF NOT EXISTS hitl_approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    proposed_action_json JSONB NOT NULL,
    agent_consensus_score DOUBLE PRECISION NOT NULL CHECK (agent_consensus_score BETWEEN 0.0 AND 1.0),
    z3_proof_hash CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_HUMAN' CHECK (
        status IN ('PENDING_HUMAN', 'APPROVED_SIGNED', 'REJECTED', 'EXPIRED')
    ),
    approver_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    ed25519_signature_hex VARCHAR(128),
    public_key_hex VARCHAR(64),
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hitl_status ON hitl_approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_hitl_created_at ON hitl_approval_requests(created_at);

-- -----------------------------------------------------------------------------
-- 3. BYZANTINE-RESILIENT FEDERATED LEARNING & DP ACCOUNTING
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS federated_rounds (
    round_number SERIAL PRIMARY KEY,
    global_weights_sha256 CHAR(64) NOT NULL,
    aggregation_algorithm VARCHAR(32) NOT NULL DEFAULT 'MULTI_KRUM_DP',
    epsilon_spent DOUBLE PRECISION NOT NULL,
    delta_param DOUBLE PRECISION NOT NULL,
    participating_nodes INT NOT NULL,
    rejected_byzantine_nodes TEXT[] NOT NULL DEFAULT '{}',
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS federated_node_submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    round_number INT NOT NULL REFERENCES federated_rounds(round_number) ON DELETE CASCADE,
    edge_node_id VARCHAR(64) NOT NULL,
    l2_norm_delta DOUBLE PRECISION NOT NULL,
    krum_distance_score DOUBLE PRECISION NOT NULL,
    accepted BOOLEAN NOT NULL,
    rejection_reason VARCHAR(128),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fed_sub_round ON federated_node_submissions(round_number);
CREATE INDEX IF NOT EXISTS idx_fed_sub_node ON federated_node_submissions(edge_node_id);

-- -----------------------------------------------------------------------------
-- 4. CRYPTOGRAPHIC MERKLE AUDIT LEDGER (Tamper-Evident Chain)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS merkle_audit_ledger (
    seq_no BIGSERIAL PRIMARY KEY,
    event_id UUID UNIQUE NOT NULL DEFAULT uuid_generate_v4(),
    event_type VARCHAR(64) NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    canonical_payload JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    prev_block_hash CHAR(64) NOT NULL,
    block_hash CHAR(64) NOT NULL,
    merkle_root_snapshot CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_merkle_block_hash ON merkle_audit_ledger(block_hash);
CREATE INDEX IF NOT EXISTS idx_merkle_prev_hash ON merkle_audit_ledger(prev_block_hash);
CREATE INDEX IF NOT EXISTS idx_merkle_created_at ON merkle_audit_ledger(created_at);

-- -----------------------------------------------------------------------------
-- 5. DETERMINISTIC SEED DATA (Genesis Block & 12 Istanbul Nodes + 18 Edges)
-- -----------------------------------------------------------------------------

-- Genesis Block for Merkle Audit Chain
INSERT INTO merkle_audit_ledger (
    seq_no,
    event_id,
    event_type,
    actor_id,
    canonical_payload,
    payload_sha256,
    prev_block_hash,
    block_hash,
    merkle_root_snapshot,
    created_at
) VALUES (
    1,
    '00000000-0000-0000-0000-000000000001',
    'GENESIS_BLOCK',
    'SYSTEM_BOOTSTRAP',
    '{"message": "NDTM v2.0 Frontier Genesis Block Initialized"}'::jsonb,
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    '0000000000000000000000000000000000000000000000000000000000000000',
    '4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b',
    '4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b',
    '2026-01-01 00:00:00Z'
) ON CONFLICT (seq_no) DO NOTHING;

-- Seed 12 Critical Infrastructure Nodes in Istanbul Metro Region
INSERT INTO infrastructure_nodes (id, node_code, node_type, location, base_failure_prob, current_health_score, capacity_kw, metadata) VALUES
('11111111-1111-1111-1111-111111111101', 'SUBSTATION_IKITELLI', 'SUBSTATION', ST_SetSRID(ST_MakePoint(28.7952, 41.0768), 4326), 0.015, 98.5, 120000.0, '{"voltage_kv": 380, "region": "Avrupa-1", "operator": "TEIAS"}'::jsonb),
('11111111-1111-1111-1111-111111111102', 'SUBSTATION_KADIKOY', 'SUBSTATION', ST_SetSRID(ST_MakePoint(29.0298, 40.9901), 4326), 0.012, 99.1, 85000.0, '{"voltage_kv": 154, "region": "Anadolu-1", "operator": "AYEDAS"}'::jsonb),
('11111111-1111-1111-1111-111111111103', 'SUBSTATION_LEVENT', 'SUBSTATION', ST_SetSRID(ST_MakePoint(29.0125, 41.0825), 4326), 0.008, 99.8, 95000.0, '{"voltage_kv": 154, "region": "Finans-Merkezi", "operator": "BEDAS"}'::jsonb),
('11111111-1111-1111-1111-111111111104', 'SUBSTATION_UMRANIYE', 'SUBSTATION', ST_SetSRID(ST_MakePoint(29.1190, 41.0255), 4326), 0.010, 97.4, 75000.0, '{"voltage_kv": 154, "region": "Anadolu-2", "operator": "AYEDAS"}'::jsonb),
('11111111-1111-1111-1111-111111111105', 'FIBER_BOGAZICI_NORTH', 'FIBER_BACKBONE', ST_SetSRID(ST_MakePoint(29.0550, 41.0850), 4326), 0.005, 100.0, 10000.0, '{"bandwidth_tbps": 80, "submarine_crossing": true}'::jsonb),
('11111111-1111-1111-1111-111111111106', 'FIBER_MARMARAY_CORE', 'FIBER_BACKBONE', ST_SetSRID(ST_MakePoint(28.9875, 41.0122), 4326), 0.004, 100.0, 12000.0, '{"bandwidth_tbps": 120, "tunnel_embedded": true}'::jsonb),
('11111111-1111-1111-1111-111111111107', 'CELL_TOWER_CAMLICA', 'CELL_TOWER', ST_SetSRID(ST_MakePoint(29.0680, 41.0280), 4326), 0.020, 96.0, 350.0, '{"antennas": 16, "5g_standalone": true}'::jsonb),
('11111111-1111-1111-1111-111111111108', 'CELL_TOWER_MASLAK', 'CELL_TOWER', ST_SetSRID(ST_MakePoint(29.0210, 41.1105), 4326), 0.018, 97.5, 280.0, '{"antennas": 12, "5g_standalone": true}'::jsonb),
('11111111-1111-1111-1111-111111111109', 'WATER_PUMP_TERKOS', 'WATER_PUMP', ST_SetSRID(ST_MakePoint(28.6750, 41.3320), 4326), 0.025, 94.0, 45000.0, '{"flow_m3_sec": 12.5, "backup_generator": true}'::jsonb),
('11111111-1111-1111-1111-111111111110', 'WATER_PUMP_OMERLI', 'WATER_PUMP', ST_SetSRID(ST_MakePoint(29.3550, 41.0450), 4326), 0.022, 95.5, 55000.0, '{"flow_m3_sec": 18.0, "backup_generator": true}'::jsonb),
('11111111-1111-1111-1111-111111111111', 'FACTORY_FURNACE_DUDULLU', 'FACTORY_FURNACE', ST_SetSRID(ST_MakePoint(29.1550, 41.0110), 4326), 0.030, 91.0, 60000.0, '{"temp_celsius": 1450, "safety_interlock": true}'::jsonb),
('11111111-1111-1111-1111-111111111112', 'FACTORY_FURNACE_TUZLA', 'FACTORY_FURNACE', ST_SetSRID(ST_MakePoint(29.3100, 40.8550), 4326), 0.028, 92.5, 72000.0, '{"temp_celsius": 1520, "safety_interlock": true}'::jsonb)
ON CONFLICT (node_code) DO NOTHING;

-- Seed 18 Directed Causal Dependency Edges (Power Feeds, Telecom, Cooling)
INSERT INTO infrastructure_edges (source_node_id, target_node_id, dependency_weight, propagation_delay_minutes, coupling_type) VALUES
-- Power Feeds from Primary Substations to Secondary/Downstream Nodes
('11111111-1111-1111-1111-111111111101', '11111111-1111-1111-1111-111111111109', 0.95, 5, 'POWER_FEED'),  -- Ikitelli powers Terkos Pump
('11111111-1111-1111-1111-111111111101', '11111111-1111-1111-1111-111111111105', 0.85, 10, 'POWER_FEED'), -- Ikitelli powers Bogazici Fiber Node
('11111111-1111-1111-1111-111111111103', '11111111-1111-1111-1111-111111111108', 0.90, 8, 'POWER_FEED'),  -- Levent powers Maslak Tower
('11111111-1111-1111-1111-111111111103', '11111111-1111-1111-1111-111111111105', 0.75, 15, 'POWER_FEED'), -- Levent redundant feed to Bogazici Fiber
('11111111-1111-1111-1111-111111111102', '11111111-1111-1111-1111-111111111106', 0.92, 5, 'POWER_FEED'),  -- Kadikoy powers Marmaray Core
('11111111-1111-1111-1111-111111111102', '11111111-1111-1111-1111-111111111107', 0.88, 12, 'POWER_FEED'), -- Kadikoy powers Camlica Tower
('11111111-1111-1111-1111-111111111104', '11111111-1111-1111-1111-111111111110', 0.94, 6, 'POWER_FEED'),  -- Umraniye powers Omerli Pump
('11111111-1111-1111-1111-111111111104', '11111111-1111-1111-1111-111111111111', 0.89, 7, 'POWER_FEED'),  -- Umraniye powers Dudullu Furnace
('11111111-1111-1111-1111-111111111104', '11111111-1111-1111-1111-111111111112', 0.82, 18, 'POWER_FEED'), -- Umraniye backup to Tuzla Furnace

-- Telecom Backhaul Dependencies
('11111111-1111-1111-1111-111111111105', '11111111-1111-1111-1111-111111111108', 0.80, 2, 'TELECOM_BACKHAUL'), -- Bogazici Fiber backhauls Maslak Tower
('11111111-1111-1111-1111-111111111106', '11111111-1111-1111-1111-111111111107', 0.85, 3, 'TELECOM_BACKHAUL'), -- Marmaray Fiber backhauls Camlica Tower
('11111111-1111-1111-1111-111111111105', '11111111-1111-1111-1111-111111111106', 0.70, 1, 'TELECOM_BACKHAUL'), -- Cross-strait backbone redundancy
('11111111-1111-1111-1111-111111111108', '11111111-1111-1111-1111-111111111103', 0.65, 5, 'TELECOM_BACKHAUL'), -- Maslak Tower telemetry to Levent Substation
('11111111-1111-1111-1111-111111111107', '11111111-1111-1111-1111-111111111104', 0.60, 5, 'TELECOM_BACKHAUL'), -- Camlica Tower telemetry to Umraniye

-- Water Cooling Supply Dependencies for High-Load Facilities
('11111111-1111-1111-1111-111111111109', '11111111-1111-1111-1111-111111111101', 0.78, 25, 'COOLING_SUPPLY'), -- Terkos water cools Ikitelli transformer bank
('11111111-1111-1111-1111-111111111110', '11111111-1111-1111-1111-111111111111', 0.88, 20, 'COOLING_SUPPLY'), -- Omerli water cools Dudullu Industrial Furnace
('11111111-1111-1111-1111-111111111110', '11111111-1111-1111-1111-111111111112', 0.91, 30, 'COOLING_SUPPLY'), -- Omerli water cools Tuzla Industrial Furnace
('11111111-1111-1111-1111-111111111109', '11111111-1111-1111-1111-111111111103', 0.68, 35, 'COOLING_SUPPLY')  -- Terkos water backup cooling for Levent
ON CONFLICT (source_node_id, target_node_id) DO NOTHING;
