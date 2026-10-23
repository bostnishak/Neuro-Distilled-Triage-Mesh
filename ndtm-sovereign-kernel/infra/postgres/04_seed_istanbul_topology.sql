-- ==============================================================================
-- NDTM-9000 SOVEREIGN KERNEL — DETERMINISTIC SEED TOPOLOGY (ISTANBUL MESH)
-- Phase 1: Physical Infrastructure SCM DAG, Field Teams, RBAC Users & Genesis Block
-- ==============================================================================

-- 1. Deterministic System Users (Password for all seed users: KernelAdmin2026!)
-- Argon2id hash for 'KernelAdmin2026!'
INSERT INTO users (id, email, password_hash, role, public_key_ed25519, is_active)
VALUES
    (
        '10000000-0000-0000-0000-000000000001',
        'architect@ndtm.kernel',
        '$argon2id$v=19$m=65536,t=3,p=4$vV4tYv65X14XmD6y61zNug$516G3yv+2+m44tU+U3N330W72Q3N42Q4vW4Q4vW4Q4v',
        'ARCHITECT',
        'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a',
        true
    ),
    (
        '10000000-0000-0000-0000-000000000002',
        'commander@ndtm.kernel',
        '$argon2id$v=19$m=65536,t=3,p=4$vV4tYv65X14XmD6y61zNug$516G3yv+2+m44tU+U3N330W72Q3N42Q4vW4Q4vW4Q4v',
        'INCIDENT_COMMANDER',
        '8a2110ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511ad75a980',
        true
    ),
    (
        '10000000-0000-0000-0000-000000000003',
        'auditor@ndtm.kernel',
        '$argon2id$v=19$m=65536,t=3,p=4$vV4tYv65X14XmD6y61zNug$516G3yv+2+m44tU+U3N330W72Q3N42Q4vW4Q4vW4Q4v',
        'AUDITOR',
        '3c964073a0ee172f3daa62325af021a68f707511ad75a9808a2110ab7d54bfed',
        true
    ),
    (
        '10000000-0000-0000-0000-000000000004',
        'operator@ndtm.kernel',
        '$argon2id$v=19$m=65536,t=3,p=4$vV4tYv65X14XmD6y61zNug$516G3yv+2+m44tU+U3N330W72Q3N42Q4vW4Q4vW4Q4v',
        'OPERATOR',
        '172f3daa62325af021a68f707511ad75a9808a2110ab7d54bfed3c964073a0ee',
        true
    )
ON CONFLICT (email) DO NOTHING;

-- 2. Field Engineering Teams (Istanbul Geographic Base Locations)
INSERT INTO field_teams (id, team_code, skills, shift_remaining_minutes, max_concurrent_tasks, base_location, current_location, is_available)
VALUES
    (
        '20000000-0000-0000-0000-000000000001',
        'TEAM_ALFA_VOLTAGE',
        ARRAY['HIGH_VOLTAGE', 'TRANSFORMER', 'SUBSTATION_SWITCHING'],
        360,
        2,
        ST_SetSRID(ST_MakePoint(29.0210, 41.1105), 4326)::geography, -- Maslak
        ST_SetSRID(ST_MakePoint(29.0210, 41.1105), 4326)::geography,
        true
    ),
    (
        '20000000-0000-0000-0000-000000000002',
        'TEAM_BRAVO_FIBER',
        ARRAY['FIBER_OPTIC', 'OTDR_TESTING', 'MICROWAVE_LINK'],
        420,
        2,
        ST_SetSRID(ST_MakePoint(28.9740, 41.0232), 4326)::geography, -- Karaköy
        ST_SetSRID(ST_MakePoint(28.9740, 41.0232), 4326)::geography,
        true
    ),
    (
        '20000000-0000-0000-0000-000000000003',
        'TEAM_CHARLIE_GAS',
        ARRAY['GAS_LEAK_CONTROL', 'HAZARDOUS_CONTAINMENT', 'PRESSURE_REGULATION'],
        300,
        1,
        ST_SetSRID(ST_MakePoint(28.9500, 41.0750), 4326)::geography, -- Alibeyköy
        ST_SetSRID(ST_MakePoint(28.9500, 41.0750), 4326)::geography,
        true
    ),
    (
        '20000000-0000-0000-0000-000000000004',
        'TEAM_DELTA_WATER',
        ARRAY['WATER_MAIN_BURST', 'HYDRO_EXCAVATION', 'PUMP_OVERHAUL'],
        480,
        2,
        ST_SetSRID(ST_MakePoint(28.6750, 41.3160), 4326)::geography, -- Terkos
        ST_SetSRID(ST_MakePoint(28.6750, 41.3160), 4326)::geography,
        true
    ),
    (
        '20000000-0000-0000-0000-000000000005',
        'TEAM_ECHO_GRID',
        ARRAY['HIGH_VOLTAGE', 'GRID_SHEDDING', 'SCADA_DIAGNOSTICS'],
        390,
        2,
        ST_SetSRID(ST_MakePoint(28.7950, 41.0742), 4326)::geography, -- İkitelli
        ST_SetSRID(ST_MakePoint(28.7950, 41.0742), 4326)::geography,
        true
    ),
    (
        '20000000-0000-0000-0000-000000000006',
        'TEAM_FOXTROT_CELL',
        ARRAY['RF_TELEMETRY', 'CELL_TOWER', 'MICROWAVE_LINK'],
        450,
        2,
        ST_SetSRID(ST_MakePoint(29.0660, 41.0280), 4326)::geography, -- Çamlıca
        ST_SetSRID(ST_MakePoint(29.0660, 41.0280), 4326)::geography,
        true
    )
ON CONFLICT (team_code) DO NOTHING;

-- 3. Istanbul 12-Node Critical Infrastructure Topological Nodes
INSERT INTO infrastructure_nodes (id, node_code, name, node_type, location, baseline_capacity, current_load, health_score, status)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'SUBSTATION_IKITELLI', 'İkitelli 380kV Ana İletim İstasyonu', 'SUBSTATION', ST_SetSRID(ST_MakePoint(28.7950, 41.0742), 4326)::geography, 800.0, 420.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000002', 'SUBSTATION_KADIKOY', 'Kadıköy 154kV Dağıtım Merkezi', 'SUBSTATION', ST_SetSRID(ST_MakePoint(29.0298, 40.9901), 4326)::geography, 450.0, 310.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000003', 'SUBSTATION_MASLAK', 'Maslak Finans Dağıtım İstasyonu', 'SUBSTATION', ST_SetSRID(ST_MakePoint(29.0210, 41.1105), 4326)::geography, 600.0, 480.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000004', 'TRANSFORMER_KARAKOY', 'Karaköy Tarihi Trafo Köşkü', 'TRANSFORMER', ST_SetSRID(ST_MakePoint(28.9740, 41.0232), 4326)::geography, 120.0, 95.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000005', 'TRANSFORMER_LEVENT', 'Levent Plaza Trafo İstasyonu', 'TRANSFORMER', ST_SetSRID(ST_MakePoint(29.0125, 41.0820), 4326)::geography, 250.0, 210.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000006', 'FIBER_BOGAZICI_NORTH', 'Boğaziçi Kuzey Denizaltı Fiber POP', 'FIBER_POP', ST_SetSRID(ST_MakePoint(29.0430, 41.0850), 4326)::geography, 1000.0, 620.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000007', 'FIBER_KADIKOY_SOUTH', 'Kadıköy Anadolu Omurga POP', 'FIBER_POP', ST_SetSRID(ST_MakePoint(29.0350, 40.9850), 4326)::geography, 800.0, 450.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000008', 'WATER_PUMP_TERKOS', 'Terkos Barajı Ana Pompa İstasyonu', 'WATER_PUMP', ST_SetSRID(ST_MakePoint(28.6750, 41.3160), 4326)::geography, 300.0, 180.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000009', 'WATER_MAIN_OMERLI', 'Ömerli İsale Hattı Basınç Odası', 'WATER_PUMP', ST_SetSRID(ST_MakePoint(29.3500, 41.0500), 4326)::geography, 350.0, 240.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000010', 'GAS_REGULATOR_ALIBEYKOY', 'Alibeyköy Doğalgaz Basınç Regülatörü', 'GAS_REGULATOR', ST_SetSRID(ST_MakePoint(28.9500, 41.0750), 4326)::geography, 500.0, 310.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000011', 'CELL_TOWER_CAMLICA', 'Çamlıca Ana Verici & Hücresel Kule', 'CELL_TOWER', ST_SetSRID(ST_MakePoint(29.0660, 41.0280), 4326)::geography, 200.0, 160.0, 1.0, 'HEALTHY'),
    ('30000000-0000-0000-0000-000000000012', 'TRAFFIC_CONTROL_YENIKAPI', 'Yenikapı Akıllı Ulaşım Kontrol Merkezi', 'TRAFFIC_CONTROL', ST_SetSRID(ST_MakePoint(28.9530, 41.0040), 4326)::geography, 150.0, 90.0, 1.0, 'HEALTHY')
ON CONFLICT (node_code) DO NOTHING;

-- 4. Directed Structural Causal Model Coupling Edges (Cascade Risk Propagation)
INSERT INTO infrastructure_edges (source_node_id, target_node_id, edge_type, coupling_strength, delay_minutes, is_severed)
VALUES
    -- Substation İkitelli powers Maslak, Karaköy, Terkos Water Pump
    ('30000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000003', 'POWER_FEED', 0.85, 3.0, false),
    ('30000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000004', 'POWER_FEED', 0.75, 5.0, false),
    ('30000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000008', 'POWER_FEED', 0.90, 4.0, false),
    
    -- Substation Maslak powers Levent and Boğaziçi North Fiber POP
    ('30000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000005', 'POWER_FEED', 0.95, 2.0, false),
    ('30000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000006', 'POWER_FEED', 0.80, 2.5, false),
    
    -- Substation Kadıköy powers Kadıköy Fiber POP, Ömerli Water Main, Çamlıca Cell Tower
    ('30000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000007', 'POWER_FEED', 0.85, 3.0, false),
    ('30000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000009', 'POWER_FEED', 0.88, 4.0, false),
    ('30000000-0000-0000-0000-000000000002', '30000000-0000-0000-0000-000000000011', 'POWER_FEED', 0.92, 2.0, false),
    
    -- Fiber Interconnects (Boğaziçi North <-> Kadıköy South, Fiber to Traffic Control)
    ('30000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000007', 'FIBER_BACKBONE', 0.95, 0.5, false),
    ('30000000-0000-0000-0000-000000000006', '30000000-0000-0000-0000-000000000012', 'SUPERVISORY_CONTROL', 0.70, 1.0, false),
    ('30000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000011', 'FIBER_BACKBONE', 0.80, 1.0, false),
    
    -- Gas Regulator feeds Substation İkitelli thermal turbines
    ('30000000-0000-0000-0000-000000000010', '30000000-0000-0000-0000-000000000001', 'GAS_POWER_INTERLOCK', 0.65, 8.0, false),
    
    -- Water Mains pressure coupling (Terkos -> Karaköy, Ömerli -> Kadıköy)
    ('30000000-0000-0000-0000-000000000008', '30000000-0000-0000-0000-000000000004', 'WATER_PRESSURE_COUPLING', 0.55, 12.0, false),
    ('30000000-0000-0000-0000-000000000009', '30000000-0000-0000-0000-000000000002', 'WATER_PRESSURE_COUPLING', 0.50, 15.0, false),
    
    -- Traffic Control depend on Levent power & Çamlıca telecommunications
    ('30000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000012', 'POWER_FEED', 0.60, 6.0, false),
    ('30000000-0000-0000-0000-000000000011', '30000000-0000-0000-0000-000000000012', 'SUPERVISORY_CONTROL', 0.75, 2.0, false),
    
    -- Redundant Feed: Maslak to Terkos SCADA telemetry
    ('30000000-0000-0000-0000-000000000003', '30000000-0000-0000-0000-000000000008', 'SUPERVISORY_CONTROL', 0.50, 4.0, false),
    ('30000000-0000-0000-0000-000000000007', '30000000-0000-0000-0000-000000000012', 'SUPERVISORY_CONTROL', 0.65, 3.0, false)
ON CONFLICT (source_node_id, target_node_id, edge_type) DO NOTHING;

-- 5. Seed Initial Genesis Merkle Block (Height 0)
INSERT INTO merkle_audit_blocks (block_height, start_seq_no, end_seq_no, event_count, merkle_root, prev_block_hash, block_hash, sealed_at, validator_signature)
VALUES
    (
        0,
        0,
        0,
        0,
        'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
        '0000000000000000000000000000000000000000000000000000000000000000',
        '4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b',
        NOW(),
        'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a0000000000000000000000000000000000000000000000000000000000000000'
    )
ON CONFLICT (block_height) DO NOTHING;
