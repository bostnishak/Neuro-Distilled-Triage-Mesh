-- =============================================================================
-- Neuro-Distilled Triage Mesh — PostgreSQL 16 + pgvector schema
--
-- Executed automatically by the postgres container on FIRST start (mounted into
-- /docker-entrypoint-initdb.d). Statements are idempotent so the file can also
-- be applied manually:  psql "$DATABASE_URL" -f database/schema.sql
--
-- NOTE: vector(768) must match EMBEDDING_DIM (multilingual-e5-base = 768,
--       bge-m3 = 1024). Change both together.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS citext;

-- ----------------------------------------------------------------------------
-- Enumerations
-- ----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE ticket_status AS ENUM (
        'pending_triage', 'triaged', 'in_progress', 'resolved', 'closed', 'triage_failed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE report_outcome AS ENUM ('created_ticket', 'merged_duplicate');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('citizen', 'operator', 'technician', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ----------------------------------------------------------------------------
-- Helpers
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- Users
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         citext      NOT NULL UNIQUE,
    display_name  text,
    role          user_role   NOT NULL DEFAULT 'citizen',
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------------------
-- Tickets (master records). Multiple reports can be merged into one ticket.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tickets (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title             text          NOT NULL,
    description       text          NOT NULL,
    category          text,                         -- user-supplied or inferred intent
    intent            text,                         -- DistillMesh prediction
    priority          smallint      CHECK (priority BETWEEN 1 AND 4),
    urgency_score     real          CHECK (urgency_score BETWEEN 0 AND 1),
    status            ticket_status NOT NULL DEFAULT 'pending_triage',
    latitude          double precision CHECK (latitude  BETWEEN -90  AND 90),
    longitude         double precision CHECK (longitude BETWEEN -180 AND 180),
    address           text,
    entities          jsonb         NOT NULL DEFAULT '[]'::jsonb,
    triage_route      text,                         -- student | teacher | heuristic
    report_count      integer       NOT NULL DEFAULT 1,
    created_by        uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at        timestamptz   NOT NULL DEFAULT now(),
    updated_at        timestamptz   NOT NULL DEFAULT now(),
    last_reported_at  timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_tickets_status_category ON tickets (status, category);
CREATE INDEX IF NOT EXISTS ix_tickets_geo ON tickets (latitude, longitude) WHERE latitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_tickets_created_at ON tickets (created_at DESC);

DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets;
CREATE TRIGGER trg_tickets_updated_at BEFORE UPDATE ON tickets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ----------------------------------------------------------------------------
-- Reports (every accepted citizen submission, original or merged duplicate)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id      uuid NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id        uuid REFERENCES users(id) ON DELETE SET NULL,
    description    text           NOT NULL,
    image_path     text,
    image_sha256   char(64),
    image_quality  jsonb,
    latitude       double precision,
    longitude      double precision,
    address        text,
    outcome        report_outcome NOT NULL,
    similarity     real,                            -- cosine similarity to master (merges)
    request_id     text,
    created_at     timestamptz    NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reports_ticket_id ON reports (ticket_id);
CREATE INDEX IF NOT EXISTS ix_reports_image_sha ON reports (image_sha256) WHERE image_sha256 IS NOT NULL;

-- ----------------------------------------------------------------------------
-- Vector embeddings (one per master ticket) — HNSW cosine index
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ticket_embeddings (
    ticket_id   uuid PRIMARY KEY REFERENCES tickets(id) ON DELETE CASCADE,
    model_name  text        NOT NULL,
    embedding   vector(768) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ticket_embeddings_hnsw
    ON ticket_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ----------------------------------------------------------------------------
-- Inference logs (DistillMesh routing telemetry)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS inference_logs (
    id          bigserial PRIMARY KEY,
    ticket_id   uuid REFERENCES tickets(id) ON DELETE SET NULL,
    route       text          NOT NULL,
    model_name  text          NOT NULL,
    intent      text,
    confidence  real,
    urgency     real,
    latency_ms  real          NOT NULL,
    cost_usd    numeric(12,6) NOT NULL DEFAULT 0,
    degraded    boolean       NOT NULL DEFAULT false,
    reasons     text[]        NOT NULL DEFAULT '{}',
    created_at  timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_inference_logs_created ON inference_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_inference_logs_route ON inference_logs (route, created_at DESC);

-- ----------------------------------------------------------------------------
-- Audit logs (append-only)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id           bigserial PRIMARY KEY,
    entity_type  text        NOT NULL,
    entity_id    text,
    action       text        NOT NULL,
    actor        text        NOT NULL DEFAULT 'system',
    details      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    request_id   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_logs (created_at DESC);

-- ----------------------------------------------------------------------------
-- User notifications (in-app inbox; delivery adapters can drain this table)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
    id            bigserial PRIMARY KEY,
    user_id       uuid REFERENCES users(id) ON DELETE CASCADE,
    ticket_id     uuid REFERENCES tickets(id) ON DELETE CASCADE,
    channel       text        NOT NULL DEFAULT 'in_app',
    message       text        NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    delivered_at  timestamptz
);

CREATE INDEX IF NOT EXISTS ix_notifications_user ON notifications (user_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- Transactional outbox: guarantees a RabbitMQ message for every committed ticket
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_events (
    id            bigserial PRIMARY KEY,
    aggregate_id  uuid        NOT NULL,
    routing_key   text        NOT NULL,
    payload       jsonb       NOT NULL,
    attempts      integer     NOT NULL DEFAULT 0,
    last_error    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    published_at  timestamptz
);

CREATE INDEX IF NOT EXISTS ix_outbox_unpublished ON outbox_events (id) WHERE published_at IS NULL;

-- ----------------------------------------------------------------------------
-- Neuro-symbolic scheduling runs (full audit trail of verified decisions)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduling_runs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status         text        NOT NULL,
    plan_source    text,
    llm_rounds     integer     NOT NULL DEFAULT 0,
    solve_time_ms  real        NOT NULL,
    request        jsonb       NOT NULL,
    result         jsonb       NOT NULL,
    request_id     text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_scheduling_runs_created ON scheduling_runs (created_at DESC);

-- ----------------------------------------------------------------------------
-- Idempotency keys (network retry safety for API POST endpoints)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key              text PRIMARY KEY,
    request_path     text        NOT NULL,
    request_hash     text        NOT NULL,
    response_status  integer     NOT NULL,
    response_headers jsonb       NOT NULL DEFAULT '{}'::jsonb,
    response_body    jsonb       NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    expires_at       timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_idempotency_expires ON idempotency_keys (expires_at);

-- ----------------------------------------------------------------------------
-- Shadow testing evaluations (continuous student vs teacher evaluation)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shadow_evaluations (
    id                 bigserial PRIMARY KEY,
    request_id         text,
    input_text         text        NOT NULL,
    student_intent     text        NOT NULL,
    teacher_intent     text        NOT NULL,
    student_confidence real,
    teacher_confidence real,
    student_urgency    real,
    teacher_urgency    real,
    intent_match       boolean     NOT NULL,
    urgency_delta      real        NOT NULL,
    divergence_score   real        NOT NULL,
    teacher_latency_ms real        NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_shadow_eval_created ON shadow_evaluations (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_shadow_intent_match ON shadow_evaluations (intent_match, created_at DESC);

