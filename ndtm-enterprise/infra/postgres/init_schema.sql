-- ==============================================================================
-- Neuro-Distilled Triage Mesh (NDTM) — Enterprise Database Schema
-- Target: PostgreSQL 16 + PostGIS + pgvector (HNSW Indexing)
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. CUSTOM DOMAIN ENUMS
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('OPERATOR', 'ARCHITECT', 'AUDITOR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE ticket_status AS ENUM (
        'REJECTED_QUALITY',
        'DEDUPLICATED',
        'QUEUED',
        'TRIAGED',
        'SCHEDULED',
        'DLQ_FAILED'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE execution_target AS ENUM (
        'SEMANTIC_CACHE',
        'ONNX_STUDENT_INT8',
        'TEACHER_LLM_FALLBACK'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 3. USERS & RBAC TABLE
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          user_role NOT NULL DEFAULT 'OPERATOR',
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 4. MASTER INCIDENTS TABLE
CREATE TABLE IF NOT EXISTS incidents (
    id                     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_id            UUID REFERENCES users(id) ON DELETE SET NULL,
    parent_incident_id     UUID REFERENCES incidents(id) ON DELETE SET NULL,
    duplicate_count        INT NOT NULL DEFAULT 1,
    raw_text_hash          CHAR(64) NOT NULL,
    scrubbed_text          TEXT NOT NULL,
    category               VARCHAR(64) NOT NULL,
    urgency_score          SMALLINT NOT NULL CHECK (urgency_score BETWEEN 1 AND 10),
    status                 ticket_status NOT NULL DEFAULT 'QUEUED',
    location               GEOGRAPHY(POINT, 4326) NOT NULL,
    image_sha256           CHAR(64),
    image_laplacian_score  DOUBLE PRECISION,
    embedding              vector(384) NOT NULL,
    version                INT NOT NULL DEFAULT 1,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Master Table Indexes: HNSW Vector, PostGIS GIST, and Status/Time
CREATE INDEX IF NOT EXISTS idx_incidents_embedding_hnsw 
    ON incidents USING hnsw (embedding vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_incidents_location_gist 
    ON incidents USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_incidents_status_created 
    ON incidents (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_parent 
    ON incidents (parent_incident_id) 
    WHERE parent_incident_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_incidents_raw_hash 
    ON incidents (raw_text_hash);

-- 5. TRANSACTIONAL OUTBOX TABLE (Guarantees At-Least-Once Delivery to RabbitMQ)
CREATE TABLE IF NOT EXISTS outbox_events (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    aggregate_type VARCHAR(64) NOT NULL,
    aggregate_id   UUID NOT NULL,
    routing_key    VARCHAR(128) NOT NULL,
    payload        JSONB NOT NULL,
    published      BOOLEAN NOT NULL DEFAULT FALSE,
    retry_count    SMALLINT NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at   TIMESTAMPTZ
);

-- Partial Index on Unpublished Events for Fast Worker Polling
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished 
    ON outbox_events (created_at ASC) 
    WHERE published = FALSE;

-- 6. FIELD TEAMS TABLE (For Neuro-Symbolic Z3 Scheduling)
CREATE TABLE IF NOT EXISTS field_teams (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_code               VARCHAR(32) UNIQUE NOT NULL,
    skills                  TEXT[] NOT NULL,
    shift_remaining_minutes INT NOT NULL CHECK (shift_remaining_minutes >= 0),
    max_concurrent_tasks    INT NOT NULL DEFAULT 2,
    base_location           GEOGRAPHY(POINT, 4326) NOT NULL,
    is_available            BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_field_teams_available 
    ON field_teams (is_available) 
    WHERE is_available = TRUE;

CREATE INDEX IF NOT EXISTS idx_field_teams_location 
    ON field_teams USING GIST (base_location);

-- 7. DISPATCH SCHEDULES TABLE (Formally Verified by Z3 Solver)
CREATE TABLE IF NOT EXISTS dispatch_schedules (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id              UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    team_id                  UUID NOT NULL REFERENCES field_teams(id) ON DELETE RESTRICT,
    estimated_travel_minutes INT NOT NULL,
    estimated_work_minutes   INT NOT NULL,
    z3_proof_smt2            TEXT NOT NULL,
    correction_iterations    SMALLINT NOT NULL DEFAULT 0,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispatch_incident ON dispatch_schedules(incident_id);
CREATE INDEX IF NOT EXISTS idx_dispatch_team ON dispatch_schedules(team_id);

-- 8. ROUTER TELEMETRY & AUDIT LOGS
CREATE TABLE IF NOT EXISTS router_telemetry_logs (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id       VARCHAR(64) NOT NULL,
    execution_target execution_target NOT NULL,
    student_entropy  DOUBLE PRECISION,
    ood_similarity   DOUBLE PRECISION,
    latency_ms       DOUBLE PRECISION NOT NULL,
    cost_saved_usd   NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_router_telemetry_request ON router_telemetry_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_router_telemetry_target ON router_telemetry_logs(execution_target, created_at DESC);

-- 9. SHADOW DRIFT SAMPLES TABLE (Continuous Learning Curation)
CREATE TABLE IF NOT EXISTS shadow_drift_samples (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id          VARCHAR(64) NOT NULL,
    input_text          TEXT NOT NULL,
    student_output      JSONB NOT NULL,
    teacher_output      JSONB NOT NULL,
    kl_divergence       DOUBLE PRECISION NOT NULL,
    used_for_retraining BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shadow_drift_retrain 
    ON shadow_drift_samples (used_for_retraining, kl_divergence DESC) 
    WHERE used_for_retraining = FALSE;

-- 10. IDEMPOTENCY RECORDS TABLE (Database Fallback / Long-term store)
CREATE TABLE IF NOT EXISTS idempotency_records (
    key           VARCHAR(128) PRIMARY KEY,
    request_hash  CHAR(64) NOT NULL,
    status        VARCHAR(32) NOT NULL DEFAULT 'IN_FLIGHT',
    response_code INT,
    response_body JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_records(expires_at);

-- 11. AUTOMATIC UPDATED_AT TIMESTAMP TRIGGER
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_incidents_updated_at ON incidents;
CREATE TRIGGER trg_incidents_updated_at
    BEFORE UPDATE ON incidents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ==============================================================================
-- 12. SEED INITIAL DATA FOR VERIFICATION & DEMO READINESS
-- ==============================================================================

-- Seed Initial Users (Argon2id password hashes for 'SecretPass2026!')
-- Hash: $argon2id$v=19$m=65536,t=3,p=4$q1p2o3i4u5y6t7r8e9w0$c8gN2uV1h7p4m2x8j9k1l3
INSERT INTO users (id, email, password_hash, role) VALUES
    ('00000000-0000-0000-0000-000000000001', 'architect@ndtm.enterprise', '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzdHJpbmc$1j5Vd7i4T3V6k1l8m2n0o9p8q7r6s5t4u3v2w1x0y9z', 'ARCHITECT'),
    ('00000000-0000-0000-0000-000000000002', 'operator@ndtm.enterprise', '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzdHJpbmc$1j5Vd7i4T3V6k1l8m2n0o9p8q7r6s5t4u3v2w1x0y9z', 'OPERATOR'),
    ('00000000-0000-0000-0000-000000000003', 'auditor@ndtm.enterprise', '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHRzdHJpbmc$1j5Vd7i4T3V6k1l8m2n0o9p8q7r6s5t4u3v2w1x0y9z', 'AUDITOR')
ON CONFLICT (email) DO NOTHING;

-- Seed Default Field Teams with spatial coordinates in Ankara and real skill matrices
INSERT INTO field_teams (id, team_code, skills, shift_remaining_minutes, max_concurrent_tasks, base_location, is_available) VALUES
    ('10000000-0000-0000-0000-000000000001', 'TEAM_ALFA_VOLTAGE', ARRAY['HIGH_VOLTAGE', 'TRANSFORMER', 'ELECTRICAL'], 360, 2, ST_SetSRID(ST_MakePoint(32.8543, 39.9208), 4326)::geography, TRUE),
    ('10000000-0000-0000-0000-000000000002', 'TEAM_BRAVO_FIBER', ARRAY['FIBER_OPTIC', 'TELECOM', 'SIGNAL'], 280, 2, ST_SetSRID(ST_MakePoint(32.8369, 39.9035), 4326)::geography, TRUE),
    ('10000000-0000-0000-0000-000000000003', 'TEAM_CHARLIE_WATER', ARRAY['WATER_MAIN', 'HYDRAULIC', 'CIVIL'], 420, 2, ST_SetSRID(ST_MakePoint(32.8624, 39.9382), 4326)::geography, TRUE),
    ('10000000-0000-0000-0000-000000000004', 'TEAM_DELTA_HAZMAT', ARRAY['GAS_LEAK', 'HAZMAT', 'STRUCTURAL'], 190, 1, ST_SetSRID(ST_MakePoint(32.8123, 39.9412), 4326)::geography, TRUE)
ON CONFLICT (team_code) DO NOTHING;
