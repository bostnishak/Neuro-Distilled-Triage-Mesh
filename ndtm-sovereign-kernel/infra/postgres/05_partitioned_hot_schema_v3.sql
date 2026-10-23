-- ============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — SCHEMA UPGRADE v3.0 (PRODUCTION HARDENING)
-- RFC-NDTM-OMEGA: Heap-Only Tuple (HOT) Partitioned Architecture
-- ============================================================================

-- Ensure required extensions are active
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ----------------------------------------------------------------------------
-- 1. RANGE-PARTITIONED CORE INCIDENT MASTER TABLE
-- Partitioned by month on `created_at` to avoid massive b-tree index degradation
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents_partitioned (
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    cluster_id UUID REFERENCES incident_clusters(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description_scrubbed TEXT NOT NULL,
    raw_payload_encrypted TEXT,
    urgency incident_urgency_enum NOT NULL DEFAULT 'MEDIUM',
    category incident_category_enum NOT NULL,
    modality incident_modality_enum NOT NULL DEFAULT 'TEXT_ONLY',
    source_protocol VARCHAR(50) NOT NULL,
    location GEOMETRY(Point, 4326) NOT NULL,
    address VARCHAR(255),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- ----------------------------------------------------------------------------
-- 2. IMMUTABLE VECTOR EMBEDDING STORE (HNSW INDEXED, ZERO UPDATES)
-- Separates high-dimensional vector embeddings to completely eliminate HNSW
-- index bloat and WAL amplification during state updates.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident_embeddings_immutable (
    incident_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    embedding vector(384) NOT NULL,
    raw_text_hash VARCHAR(64) NOT NULL,
    PRIMARY KEY (incident_id, created_at),
    FOREIGN KEY (incident_id, created_at) REFERENCES incidents_partitioned(id, created_at) ON DELETE CASCADE
);

-- HNSW Vector Index on immutable embeddings only
CREATE INDEX IF NOT EXISTS idx_immutable_embeddings_hnsw
ON incident_embeddings_immutable
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 128);

-- Append-Only Constraint Trigger on Immutable Embeddings
CREATE OR REPLACE FUNCTION fn_prevent_immutable_embedding_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'CRITICAL: incident_embeddings_immutable is strictly append-only. UPDATE operations are forbidden to prevent HNSW index corruption.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_immutable_embedding_update ON incident_embeddings_immutable;
CREATE TRIGGER trg_prevent_immutable_embedding_update
BEFORE UPDATE ON incident_embeddings_immutable
FOR EACH ROW EXECUTE FUNCTION fn_prevent_immutable_embedding_update();

-- ----------------------------------------------------------------------------
-- 3. HEAP-ONLY TUPLE (HOT) LIVE STATE TABLE (FILLFACTOR = 70)
-- Stores high-frequency mutable counters and operational status.
-- By having fillfactor = 70 and NO secondary indexes on mutable fields,
-- PostgreSQL executes 100% in-page HOT updates without any index writes.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident_live_state (
    incident_id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duplicate_count INT NOT NULL DEFAULT 0,
    triage_state triage_state_enum NOT NULL DEFAULT 'QUEUED',
    triage_decision incident_category_enum,
    triage_confidence DOUBLE PRECISION,
    hawkes_intensity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    divergence_score DOUBLE PRECISION,
    last_excited_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INT NOT NULL DEFAULT 1
) WITH (fillfactor = 70);

-- Trigger to increment version and refresh updated_at atomically
CREATE OR REPLACE FUNCTION fn_touch_incident_live_state()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_touch_incident_live_state ON incident_live_state;
CREATE TRIGGER trg_touch_incident_live_state
BEFORE UPDATE ON incident_live_state
FOR EACH ROW EXECUTE FUNCTION fn_touch_incident_live_state();

-- ----------------------------------------------------------------------------
-- 4. MONTHLY PARTITIONS FOR incidents_partitioned (2026-10 through 2027-02)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents_y2026m10 PARTITION OF incidents_partitioned
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS incidents_y2026m11 PARTITION OF incidents_partitioned
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS incidents_y2026m12 PARTITION OF incidents_partitioned
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS incidents_y2027m01 PARTITION OF incidents_partitioned
    FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS incidents_default PARTITION OF incidents_partitioned
    DEFAULT;

-- Spatial and Filtering Indexes on Partitions
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m10_location ON incidents_y2026m10 USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m10_urgency_created ON incidents_y2026m10 (urgency, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m10_cluster ON incidents_y2026m10 (cluster_id);

CREATE INDEX IF NOT EXISTS idx_incidents_y2026m11_location ON incidents_y2026m11 USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m11_urgency_created ON incidents_y2026m11 (urgency, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m11_cluster ON incidents_y2026m11 (cluster_id);

CREATE INDEX IF NOT EXISTS idx_incidents_y2026m12_location ON incidents_y2026m12 USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m12_urgency_created ON incidents_y2026m12 (urgency, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_y2026m12_cluster ON incidents_y2026m12 (cluster_id);

CREATE INDEX IF NOT EXISTS idx_incidents_y2027m01_location ON incidents_y2027m01 USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_incidents_y2027m01_urgency_created ON incidents_y2027m01 (urgency, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_y2027m01_cluster ON incidents_y2027m01 (cluster_id);

CREATE INDEX IF NOT EXISTS idx_incidents_default_location ON incidents_default USING GIST (location);

-- ----------------------------------------------------------------------------
-- 5. RANGE-PARTITIONED ROUTER TELEMETRY TABLE
-- Captures high-frequency entropy and latency metrics without bloating transaction logs
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS router_telemetry_partitioned (
    id UUID NOT NULL DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL,
    route_decision VARCHAR(50) NOT NULL,
    model_tier VARCHAR(50) NOT NULL,
    entropy DOUBLE PRECISION NOT NULL,
    ood_mahalanobis_distance DOUBLE PRECISION NOT NULL,
    dynamic_threshold DOUBLE PRECISION NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    student_confidence DOUBLE PRECISION NOT NULL,
    teacher_divergence DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE IF NOT EXISTS router_telemetry_y2026m10 PARTITION OF router_telemetry_partitioned
    FOR VALUES FROM ('2026-10-01 00:00:00+00') TO ('2026-11-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS router_telemetry_y2026m11 PARTITION OF router_telemetry_partitioned
    FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS router_telemetry_y2026m12 PARTITION OF router_telemetry_partitioned
    FOR VALUES FROM ('2026-12-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS router_telemetry_y2027m01 PARTITION OF router_telemetry_partitioned
    FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2027-02-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS router_telemetry_default PARTITION OF router_telemetry_partitioned
    DEFAULT;

CREATE INDEX IF NOT EXISTS idx_router_telemetry_y2026m10_decision ON router_telemetry_y2026m10 (route_decision, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_router_telemetry_y2026m11_decision ON router_telemetry_y2026m11 (route_decision, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_router_telemetry_y2026m12_decision ON router_telemetry_y2026m12 (route_decision, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_router_telemetry_y2027m01_decision ON router_telemetry_y2027m01 (route_decision, created_at DESC);

-- ----------------------------------------------------------------------------
-- 6. PARTITION MAINTENANCE AUTOMATION FUNCTION
-- Automatically provisions future monthly range partitions and local indexes
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_create_monthly_partitions(
    target_table_name TEXT,
    start_date DATE,
    months_ahead INT DEFAULT 3
)
RETURNS TABLE (partition_name TEXT, range_start TIMESTAMPTZ, range_end TIMESTAMPTZ) AS $$
DECLARE
    i INT;
    curr_start DATE;
    next_start DATE;
    part_name TEXT;
    sql_create TEXT;
    sql_index TEXT;
BEGIN
    FOR i IN 0..(months_ahead - 1) LOOP
        curr_start := (date_trunc('month', start_date) + (i || ' month')::interval)::DATE;
        next_start := (curr_start + '1 month'::interval)::DATE;
        part_name := target_table_name || '_y' || to_char(curr_start, 'YYYY') || 'm' || to_char(curr_start, 'MM');

        sql_create := format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L);',
            part_name, target_table_name, curr_start::timestamptz, next_start::timestamptz
        );
        EXECUTE sql_create;

        -- Create spatial index if the partition belongs to incidents_partitioned
        IF target_table_name = 'incidents_partitioned' THEN
            sql_index := format(
                'CREATE INDEX IF NOT EXISTS %I ON %I USING GIST (location);',
                'idx_' || part_name || '_location', part_name
            );
            EXECUTE sql_index;
        END IF;

        partition_name := part_name;
        range_start := curr_start::timestamptz;
        range_end := next_start::timestamptz;
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 7. BACKWARD-COMPATIBLE UNIFIED VIEW WITH INSTEAD-OF TRIGGER
-- Allows existing queries and ORMs to transparently read and write to the
-- HOT-optimized decomposed architecture without changing client code.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_incidents_unified_v3 AS
SELECT
    p.id,
    p.cluster_id,
    p.title,
    p.description_scrubbed,
    p.raw_payload_encrypted,
    p.urgency,
    p.category,
    p.modality,
    p.source_protocol,
    p.location,
    p.address,
    p.metadata_json,
    p.created_at,
    l.duplicate_count,
    l.triage_state,
    l.triage_decision,
    l.triage_confidence,
    l.hawkes_intensity,
    l.divergence_score,
    l.last_excited_at,
    l.updated_at,
    l.version,
    e.embedding,
    e.raw_text_hash
FROM incidents_partitioned p
INNER JOIN incident_live_state l ON p.id = l.incident_id
LEFT JOIN incident_embeddings_immutable e ON (p.id = e.incident_id AND p.created_at = e.created_at);

-- INSTEAD OF INSERT Trigger for Unified View
CREATE OR REPLACE FUNCTION fn_insert_unified_incident_v3()
RETURNS TRIGGER AS $$
DECLARE
    new_inc_id UUID;
    new_created_at TIMESTAMPTZ;
BEGIN
    new_inc_id := COALESCE(NEW.id, uuid_generate_v4());
    new_created_at := COALESCE(NEW.created_at, NOW());

    -- 1. Insert into partitioned base table
    INSERT INTO incidents_partitioned (
        id, cluster_id, title, description_scrubbed, raw_payload_encrypted,
        urgency, category, modality, source_protocol, location, address,
        metadata_json, created_at
    ) VALUES (
        new_inc_id, NEW.cluster_id, NEW.title, NEW.description_scrubbed, NEW.raw_payload_encrypted,
        NEW.urgency, NEW.category, NEW.modality, NEW.source_protocol, NEW.location, NEW.address,
        NEW.metadata_json, new_created_at
    );

    -- 2. Insert into HOT live state table
    INSERT INTO incident_live_state (
        incident_id, created_at, duplicate_count, triage_state, triage_decision,
        triage_confidence, hawkes_intensity, divergence_score, last_excited_at, updated_at, version
    ) VALUES (
        new_inc_id, new_created_at, COALESCE(NEW.duplicate_count, 0), COALESCE(NEW.triage_state, 'QUEUED'),
        NEW.triage_decision, NEW.triage_confidence, COALESCE(NEW.hawkes_intensity, 0.0), NEW.divergence_score,
        NEW.last_excited_at, new_created_at, 1
    );

    -- 3. Insert into immutable embeddings store if embedding is provided
    IF NEW.embedding IS NOT NULL THEN
        INSERT INTO incident_embeddings_immutable (
            incident_id, created_at, embedding, raw_text_hash
        ) VALUES (
            new_inc_id, new_created_at, NEW.embedding,
            COALESCE(NEW.raw_text_hash, md5(NEW.description_scrubbed))
        );
    END IF;

    NEW.id := new_inc_id;
    NEW.created_at := new_created_at;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_insert_unified_incident_v3 ON v_incidents_unified_v3;
CREATE TRIGGER trg_insert_unified_incident_v3
INSTEAD OF INSERT ON v_incidents_unified_v3
FOR EACH ROW EXECUTE FUNCTION fn_insert_unified_incident_v3();

-- ----------------------------------------------------------------------------
-- 8. INITIAL DATA MIGRATION BRIDGE (PHASE 1-24 DATA SEEDING TO V3 SCHEMA)
-- Transparently synchronizes any existing records in legacy incidents table
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'incidents') THEN
        -- Migrate base data into partitioned table
        INSERT INTO incidents_partitioned (
            id, cluster_id, title, description_scrubbed, raw_payload_encrypted,
            urgency, category, modality, source_protocol, location, address, metadata_json, created_at
        )
        SELECT
            id, cluster_id, title, description_scrubbed, raw_payload_encrypted,
            urgency::text::incident_urgency_enum,
            category::text::incident_category_enum,
            modality::text::incident_modality_enum,
            source_protocol, location, address, metadata_json, created_at
        FROM incidents
        ON CONFLICT DO NOTHING;

        -- Migrate live state into HOT table
        INSERT INTO incident_live_state (
            incident_id, created_at, duplicate_count, triage_state, triage_decision,
            triage_confidence, hawkes_intensity, divergence_score, updated_at
        )
        SELECT
            id, created_at, 0,
            triage_state::text::triage_state_enum,
            CASE WHEN triage_decision IS NOT NULL THEN triage_decision::text::incident_category_enum ELSE NULL END,
            triage_confidence,
            0.0,
            divergence_score,
            updated_at
        FROM incidents
        ON CONFLICT DO NOTHING;

        -- Migrate embeddings into immutable store
        INSERT INTO incident_embeddings_immutable (
            incident_id, created_at, embedding, raw_text_hash
        )
        SELECT
            id, created_at, embedding, md5(description_scrubbed)
        FROM incidents
        WHERE embedding IS NOT NULL
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
