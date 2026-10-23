# NDTM-9000 OMEGA: SOVEREIGN PRODUCTION IMPLEMENTATION & REMEDIATION PLAN

**Document Classification:** Production Hardening & Remediation Blueprint  
**Target Systems:** NDTM-9000 Sovereign Kernel (FastAPI, C++20 Edge, Z3 SMT, ONNX INT8, React Cockpit)  
**Status:** ACTIVE EXECUTION  

---

## 1. DEFECT REMEDIATION MATRIX (AUDIT FINDINGS)

| Defect ID | Subsystem | Severity | Description & Root Cause | Exact Engineering Fix | Status |
| :--- | :--- | :---: | :--- | :--- | :---: |
| **DEF-01** | `onnx_runtime_engine` | CRITICAL | ONNX fallback previously synthesized pseudo-random predictions on missing model session. | Throws `ModelUnavailableError` immediately. Integrated Genesis bootstrapper generates verified quantized baseline `models/student_quantized.onnx`. | **RESOLVED** |
| **DEF-02** | `security_ed25519_jwt` | CRITICAL | Asymmetric authentication library could fall back to symmetric HMAC if `cryptography` was absent. | Enforced strict fail-closed asymmetric signing in `Ed25519Signer`. Raises fatal exception on missing libsodium/cryptography primitives; zero HMAC fallback. | **RESOLVED** |
| **DEF-03** | `main.py` / `mcp_server` | HIGH | `/api/v3/*` and `/mcp/rpc` endpoints were exposed without RBAC authentication dependency guards. | Mounted `Depends(require_role("ADMIN"))` across `/api/v3/sre` and `/api/v3/crdt`. Bound `Depends(get_current_user)` to MCP JSON-RPC gateway. | **RESOLVED** |
| **DEF-04** | `automated_dr_backup_verifier` | MEDIUM | Disaster recovery audit endpoint returned synthetic mock evaluation without verifying physical WAL continuity. | Upgraded to SQLite/PostgreSQL in-memory sandbox verification with real byte stream hashing, transaction playback, and checksum assertion. | **RESOLVED** |
| **DEF-05** | `frontend/api.ts` & Views 11/12 | MEDIUM | Frontend views caught backend network exceptions and masked failures with hardcoded mock telemetry. | Refactored `api.ts` to surface true backend errors; wired real Canary judge and Multi-Region CRDT replication endpoints to Cockpit state. | **RESOLVED** |

---

## 2. 52-WEEK PHASE-BY-PHASE EXECUTION ARCHITECTURE

* **Quarter 1 (Weeks 1–13):** Foundation, Core Architecture, HOT Tables, C++20 SeqLock IPC, and Transactional Outbox.
* **Quarter 2 (Weeks 14–26):** DistillMesh Semantic Router, Knowledge Distillation Forge, Subprocess Z3 MaxSMT Solver, and RuleLang SMT Engine.
* **Quarter 3 (Weeks 27–39):** PgBouncer HA Pooling, Markovian H3 Hawkes Mesh, Active-Active CRDT Replicator, and Micro-Batched MMR Ledger.
* **Quarter 4 (Weeks 40–52):** Carrier-Grade Chaos Hardening, Kubernetes Argo Rollouts, SRE Multi-Burn Rate Alerting, and Production Genesis.
