-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — POSTGRESQL EXTENSIONS & DOMAIN ENUMS
-- Phase 1: Core Extensions, Spatial Geometries & Algebraic Types
-- ==============================================================================

-- 1. Enable Required Enterprise Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. Domain Role-Based Access Control (RBAC) Enumeration
DO $$ BEGIN
    CREATE TYPE user_role_enum AS ENUM (
        'OPERATOR',
        'DISPATCHER',
        'INCIDENT_COMMANDER',
        'ARCHITECT',
        'AUDITOR'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 3. Multimodal Incident Category Taxonomy
DO $$ BEGIN
    CREATE TYPE incident_category_enum AS ENUM (
        'POWER_GRID_FAILURE',
        'TRANSFORMER_FIRE',
        'GAS_LEAK',
        'WATER_MAIN_BURST',
        'FIBER_CUT',
        'ROAD_COLLAPSE',
        'SIGNAL_INTERFERENCE',
        'CYBER_TELEMETRY_ANOMALY'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 4. Incident Lifecycle State Machine
DO $$ BEGIN
    CREATE TYPE incident_status_enum AS ENUM (
        'TRIAGED',
        'CLUSTER_ABSORBED',
        'SCHEDULED',
        'DISPATCHED',
        'RESOLVED',
        'FALSE_ALARM'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 5. Control-Theoretic Execution & Inference Target
DO $$ BEGIN
    CREATE TYPE execution_target_enum AS ENUM (
        'ONNX_STUDENT_INT8',
        'TEACHER_LLM_FALLBACK',
        'SEMANTIC_CACHE',
        'SPECULATIVE_RESAMPLED'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 6. Upstream Circuit Breaker Finite State Machine
DO $$ BEGIN
    CREATE TYPE circuit_state_enum AS ENUM (
        'CLOSED',
        'OPEN',
        'HALF_OPEN'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 7. Causal Digital Twin Physical Node Taxonomy
DO $$ BEGIN
    CREATE TYPE infrastructure_node_type_enum AS ENUM (
        'SUBSTATION',
        'TRANSFORMER',
        'FIBER_POP',
        'WATER_PUMP',
        'GAS_REGULATOR',
        'CELL_TOWER',
        'TRAFFIC_CONTROL'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 8. Infrastructure Operational & Health States
DO $$ BEGIN
    CREATE TYPE node_operational_status_enum AS ENUM (
        'HEALTHY',
        'DEGRADED',
        'FAILED',
        'REINFORCED',
        'ISOLATED'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 9. Directed Physical Coupling Types for Structural Causal Model
DO $$ BEGIN
    CREATE TYPE edge_coupling_type_enum AS ENUM (
        'POWER_FEED',
        'FIBER_BACKBONE',
        'SUPERVISORY_CONTROL',
        'WATER_PRESSURE_COUPLING',
        'GAS_POWER_INTERLOCK'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 10. Human-in-the-Loop (HITL) Cryptographic Approval States
DO $$ BEGIN
    CREATE TYPE hitl_approval_status_enum AS ENUM (
        'PENDING_HUMAN',
        'APPROVED_SIGNED',
        'REJECTED_DISMISSED',
        'AUTO_EXPIRED'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 11. Event Sourced Universe Branch Discriminator
DO $$ BEGIN
    CREATE TYPE event_universe_branch_enum AS ENUM (
        'MAIN_TIMELINE',
        'COUNTERFACTUAL_FORK'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 12. Pareto-Optimal Multi-Objective Dispatch Archetypes
DO $$ BEGIN
    CREATE TYPE pareto_plan_enum AS ENUM (
        'SPEED_FIRST',
        'BALANCED',
        'COST_ENDURANCE'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
