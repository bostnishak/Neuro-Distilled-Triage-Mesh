-- =============================================================================
-- Neuro-Distilled Triage Mesh (NDTM) — Database Schema
-- PostgreSQL 16 + pgvector extension
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS citext;

-- ----------------------------------------------------------------------------
-- 1. Users Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           citext NOT NULL UNIQUE,
    hashed_password text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 2. Tickets Table
-- ----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE ticket_lifecycle_status AS ENUM (
        'pending', 'processing', 'resolved', 'escalated'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS tickets (
    id                  uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             uuid REFERENCES users(id) ON DELETE SET NULL,
    raw_description     text NOT NULL,
    cleaned_description text NOT NULL,
    image_url           text,
    category            text,
    urgency_score       real CHECK (urgency_score BETWEEN 0.0 AND 1.0),
    status              ticket_lifecycle_status NOT NULL DEFAULT 'pending',
    report_count        integer NOT NULL DEFAULT 1,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS ix_tickets_category ON tickets(category);
CREATE INDEX IF NOT EXISTS ix_tickets_created_at ON tickets(created_at DESC);

-- ----------------------------------------------------------------------------
-- 3. Ticket Embeddings (pgvector HNSW Cosine Index)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_embeddings (
    id         bigserial PRIMARY KEY,
    ticket_id  uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    embedding  vector(768) NOT NULL,
    metadata   jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ticket_embeddings_hnsw
    ON ticket_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS ix_ticket_embeddings_ticket_id ON ticket_embeddings(ticket_id);

-- ----------------------------------------------------------------------------
-- 4. Audit Logs Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id             bigserial PRIMARY KEY,
    request_id     text NOT NULL,
    endpoint       text NOT NULL,
    latency_ms     real NOT NULL,
    token_counts   integer NOT NULL DEFAULT 0,
    execution_path text NOT NULL CHECK (execution_path IN ('onnx_student', 'teacher_llm', 'semantic_cache', 'heuristic')),
    cost_usd       numeric(12, 6) NOT NULL DEFAULT 0.0,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_request_id ON audit_logs(request_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs(created_at DESC);

-- ----------------------------------------------------------------------------
-- 5. Fine-Tuning Candidates (Active Learning Collection)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fine_tuning_candidates (
    id               bigserial PRIMARY KEY,
    input_prompt     text NOT NULL,
    student_output   jsonb NOT NULL,
    teacher_output   jsonb NOT NULL,
    divergence_score real NOT NULL,
    processed        boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ft_candidates_unprocessed 
    ON fine_tuning_candidates(processed, divergence_score DESC) 
    WHERE processed = false;

-- ----------------------------------------------------------------------------
-- 6. Idempotency Keys Table
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key              text PRIMARY KEY,
    response_payload jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 7. Human-in-the-Loop Review Tasks (Multi-Agent Consensus Fallback)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hitl_review_tasks (
    id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    ticket_id         uuid REFERENCES tickets(id) ON DELETE CASCADE,
    agent_name        text NOT NULL,
    consensus_score   real NOT NULL,
    workflow_state    jsonb NOT NULL,
    assigned_reviewer text,
    resolution_notes  text,
    status            text NOT NULL DEFAULT 'pending_review',
    created_at        timestamptz NOT NULL DEFAULT now(),
    resolved_at       timestamptz
);

CREATE INDEX IF NOT EXISTS ix_hitl_tasks_status ON hitl_review_tasks(status, created_at DESC);
