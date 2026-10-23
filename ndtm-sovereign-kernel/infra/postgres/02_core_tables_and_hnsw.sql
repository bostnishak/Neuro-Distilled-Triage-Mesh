-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — CORE RELATIONAL SCHEMA & HNSW VECTOR INDICES
-- Phase 1: Incidents, Hawkes Clusters, Dispatch, Outbox & Infrastructure Graph
-- ==============================================================================

-- 1. Security & Identity Table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role user_role_enum NOT NULL DEFAULT 'OPERATOR',
    public_key_ed25519 VARCHAR(64) DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- 2. Multimodal Incident Ingestion Table (Vector + Spatial Geodesic)
CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_incident_id UUID REFERENCES incidents(id) ON DELETE SET NULL,
    duplicate_count INT NOT NULL DEFAULT 1,
    raw_description TEXT NOT NULL,
    scrubbed_description TEXT NOT NULL,
    category incident_category_enum NOT NULL,
    urgency_score INT NOT NULL CHECK (urgency_score BETWEEN 1 AND 10),
    confidence FLOAT8 NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    routing_entropy FLOAT8 NOT NULL DEFAULT 0.0,
    mahalanobis_distance FLOAT8 NOT NULL DEFAULT 0.0,
    execution_target execution_target_enum NOT NULL DEFAULT 'ONNX_STUDENT_INT8',
    embedding vector(384) NOT NULL,
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    spatial_centroid GEOGRAPHY(POINT, 4326) NOT NULL,
    status incident_status_enum NOT NULL DEFAULT 'TRIAGED',
    laplacian_variance FLOAT8 NOT NULL DEFAULT 0.0,
    spectral_entropy FLOAT8 NOT NULL DEFAULT 0.0,
    mel_fingerprint FLOAT4[] DEFAULT NULL,
    image_sha256 VARCHAR(64) DEFAULT NULL,
    reporter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW Vector Indexing for Fast Sub-Millisecond Cosine Similarity
CREATE INDEX IF NOT EXISTS idx_incidents_embedding_hnsw 
ON incidents USING hnsw (embedding vector_cosine_ops) 
WITH (m = 16, ef_construction = 64);

-- PostGIS Spatial Indices
CREATE INDEX IF NOT EXISTS idx_incidents_location_gist 
ON incidents USING gist (location);

CREATE INDEX IF NOT EXISTS idx_incidents_centroid_gist 
ON incidents USING gist (spatial_centroid);

CREATE INDEX IF NOT EXISTS idx_incidents_status_urgency 
ON incidents (status, urgency_score DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_parent_id 
ON incidents (parent_incident_id) WHERE parent_incident_id IS NOT NULL;

-- 3. Spatio-Temporal Hawkes Process Cluster History
CREATE TABLE IF NOT EXISTS incident_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    absorbed_incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    hawkes_intensity FLOAT8 NOT NULL,
    spatial_dist_meters FLOAT8 NOT NULL,
    cosine_similarity FLOAT8 NOT NULL,
    absorbed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clusters_parent ON incident_clusters (parent_incident_id);
CREATE INDEX IF NOT EXISTS idx_clusters_absorbed ON incident_clusters (absorbed_incident_id);

-- 4. Mobile Engineering Field Teams
CREATE TABLE IF NOT EXISTS field_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_code VARCHAR(32) UNIQUE NOT NULL,
    skills TEXT[] NOT NULL,
    shift_remaining_minutes INT NOT NULL CHECK (shift_remaining_minutes >= 0),
    max_concurrent_tasks INT NOT NULL DEFAULT 2 CHECK (max_concurrent_tasks >= 1),
    base_location GEOGRAPHY(POINT, 4326) NOT NULL,
    current_location GEOGRAPHY(POINT, 4326) NOT NULL,
    is_available BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_teams_location_gist 
ON field_teams USING gist (current_location);

CREATE INDEX IF NOT EXISTS idx_field_teams_availability 
ON field_teams (is_available) WHERE is_available = true;

-- 5. Neuro-Symbolic Pareto-Optimal Dispatch Schedules
CREATE TABLE IF NOT EXISTS dispatch_schedules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES field_teams(id) ON DELETE RESTRICT,
    pareto_plan_type pareto_plan_enum NOT NULL DEFAULT 'BALANCED',
    estimated_travel_minutes INT NOT NULL CHECK (estimated_travel_minutes >= 0),
    estimated_work_minutes INT NOT NULL CHECK (estimated_work_minutes >= 0),
    arrival_time_minutes INT NOT NULL CHECK (arrival_time_minutes >= 0),
    objective_speed_score FLOAT8 NOT NULL,
    objective_cost_score FLOAT8 NOT NULL,
    z3_proof_smt2 TEXT NOT NULL,
    z3_proof_hash VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    dispatched_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_incident ON dispatch_schedules (incident_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_team ON dispatch_schedules (team_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_status ON dispatch_schedules (status);

-- 6. Transactional Outbox Queue (Guaranteed Broker Delivery)
CREATE TABLE IF NOT EXISTS transactional_outbox (
    id BIGSERIAL PRIMARY KEY,
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    routing_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    retry_count INT NOT NULL DEFAULT 0,
    last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished 
ON transactional_outbox (created_at ASC) 
WHERE published_at IS NULL;

-- 7. Structural Causal Model Infrastructure Nodes
CREATE TABLE IF NOT EXISTS infrastructure_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    node_type infrastructure_node_type_enum NOT NULL,
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    baseline_capacity FLOAT8 NOT NULL DEFAULT 100.0,
    current_load FLOAT8 NOT NULL DEFAULT 50.0,
    health_score FLOAT8 NOT NULL DEFAULT 1.0 CHECK (health_score >= 0.0 AND health_score <= 1.0),
    status node_operational_status_enum NOT NULL DEFAULT 'HEALTHY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_infra_nodes_location_gist 
ON infrastructure_nodes USING gist (location);

CREATE INDEX IF NOT EXISTS idx_infra_nodes_status 
ON infrastructure_nodes (status);

-- 8. Structural Causal Model Directed Coupling Edges
CREATE TABLE IF NOT EXISTS infrastructure_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL REFERENCES infrastructure_nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES infrastructure_nodes(id) ON DELETE CASCADE,
    edge_type edge_coupling_type_enum NOT NULL,
    coupling_strength FLOAT8 NOT NULL CHECK (coupling_strength >= 0.0 AND coupling_strength <= 1.0),
    delay_minutes FLOAT8 NOT NULL DEFAULT 5.0,
    is_severed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_infra_edge UNIQUE(source_node_id, target_node_id, edge_type)
);

CREATE INDEX IF NOT EXISTS idx_infra_edges_source_target 
ON infrastructure_edges (source_node_id, target_node_id);

-- ==============================================================================
-- Multi-Tenancy & Row-Level Security (RLS) Isolation (RFC-NDTM Finding 8)
-- ==============================================================================
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000';
CREATE INDEX IF NOT EXISTS idx_incidents_tenant_id ON incidents (tenant_id);

ALTER TABLE incidents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS p_incidents_tenant_isolation ON incidents;
CREATE POLICY p_incidents_tenant_isolation ON incidents
    USING (
        current_setting('app.current_tenant', true) IS NULL 
        OR current_setting('app.current_tenant', true) = '' 
        OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::UUID
    );
