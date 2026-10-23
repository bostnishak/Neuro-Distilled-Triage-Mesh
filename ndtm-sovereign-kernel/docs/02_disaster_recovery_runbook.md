# NDTM-9000 OMEGA: DISASTER RECOVERY & SPLIT-BRAIN RESILIENCE RUNBOOK
**Document Version:** 3.0.0-DR  
**Classification:** Sovereign Business Continuity & Zero-Data-Loss Plan  
**Target RPO:** $\le 12.0\text{ seconds}$ | **Target RTO:** $\le 120.0\text{ seconds}$  

---

## 1. AUTOMATED CONTINUOUS WAL & BASEBACKUP AUDIT

The system runs automated continuous DR probes via `AutomatedDRBackupVerifier`:
```bash
curl -X POST http://localhost:8001/api/v3/sre/dr-audit \
  -H "Authorization: Bearer $ADMIN_JWT_TOKEN" | jq .
```
Expected output:
```json
{
  "mode": "SANDBOX_RESTORATION_VERIFIED",
  "backup_id": "backup_prod_001",
  "status": "COMPLIANT",
  "basebackup_valid": true,
  "wal_continuity_valid": true,
  "sandbox_restore_success": true,
  "records_verified_count": 3,
  "rpo_seconds_achieved": 12.0,
  "rto_seconds_achieved": 4.2
}
```

---

## 2. WAN NETWORK PARTITION & CRDT CONVERGENCE RECOVERY

When cross-region BGP routes fail between `us-west-1`, `eu-central-1`, and `ap-southeast-1`:

### Phase 1: Autonomous Local State Buffering
* Each regional cluster falls back to local CRDT semilattices:
  * Incidents open and transition using local VectorClocks: $\mathbf{V}_{\text{local}}[R] \leftarrow \mathbf{V}_{\text{local}}[R] + 1$.
  * All mutations append to the local LWW-Element-Set.
  * Zero cross-region blocking locks or timeouts.

### Phase 2: WAN Link Restored & Delta Exchange
Execute state reconciliation trigger:
```bash
curl -X POST http://localhost:8001/api/v3/crdt/simulate-wan-partition \
  -H "Authorization: Bearer $ADMIN_JWT_TOKEN" | jq .
```
* **Convergence Proof:** The join-semilattice merges all regional states:
  $$\mathbf{S}_{\text{converged}} = \mathbf{S}_{\text{US}} \sqcup \mathbf{S}_{\text{EU}} \sqcup \mathbf{S}_{\text{AP}}$$
* `mathematically_converged: true` confirms 100% data consistency without split-brain corruption.

---

## 3. PHYSICAL REGIONAL FAILOVER PROCEDURE (POSTGRESQL HA)

If the primary PostgreSQL host suffers catastrophic hardware destruction:
1. Promote standby replica to primary:
   ```bash
   pg_ctl promote -D /var/lib/postgresql/data
   ```
2. Reconfigure PgBouncer target to promoted node:
   ```bash
   psql -p 6432 -U pgbouncer -d pgbouncer -c "RELOAD;"
   ```
3. Verify connection pool routing:
   ```bash
   curl -s http://localhost:8001/api/v3/sre/db-routing | jq .
   ```
