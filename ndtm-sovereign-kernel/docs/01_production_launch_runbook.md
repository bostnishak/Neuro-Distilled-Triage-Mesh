# NDTM-9000 OMEGA: CARRIER-GRADE PRODUCTION LAUNCH RUNBOOK
**Document Version:** 3.0.0-PROD  
**Classification:** Mission-Critical Infrastructure Operations  
**Target Architecture:** Multi-AZ Kubernetes (EKS/GKE) + PgBouncer HA + RabbitMQ Clustered Mesh  

---

## 1. PRE-FLIGHT READINESS & GO/NO-GO GATES

### Gate 1: Cryptographic Model Supply Chain Verification
Execute preflight signature validation for all quantized models:
```bash
python -c "from backend.core.model_supply_chain_signer import ModelSupplyChainSigner; \
signer = ModelSupplyChainSigner(); \
print('Manifest Status:', signer.verify_model_artifact('models/student_quantized.onnx', 'models/manifest.json'))"
```
* **Criterion:** Return `VERIFIED_GENUINE_SOVEREIGN_ARTIFACT`. Zero unverified weights allowed.

### Gate 2: Database HOT Partitioning & PgBouncer Health
```bash
# Verify PgBouncer connection pooling
psql "postgresql://ndtm_kernel:$POSTGRES_PASSWORD@127.0.0.1:6432/ndtm_sovereign_db" -c \
  "SHOW POOLS; SELECT count(*) FROM incident_live_state;"
```
* **Criterion:** Active server connections $\le 200$; pool utilization $\le 65\%$.

### Gate 3: SRE Readiness & SLO Multi-Burn Probe
```bash
curl -fsS http://localhost:8001/api/v3/sre/readiness | jq .
```
* **Criterion:** Status `READY`, `p99_latency_ms <= 15.0`, `error_budget_remaining >= 99.8%`.

---

## 2. PRODUCTION ROLLOUT PIPELINE (ARGO ROLLOUTS CANARY)

### Step 2.1: Initial 10% Canary Injection
```bash
kubectl argo rollouts set image ndtm-backend backend=ndtm-sovereign/backend:v3.0.0 -n ndtm-system
kubectl argo rollouts promote ndtm-backend --step 1 -n ndtm-system
```

### Step 2.2: Automated Kolmogorov-Smirnov (KS) Drift Evaluation
The Argo AnalysisTemplate automatically queries `/api/v3/sre/canary-judge`:
* Two-sample KS test evaluated over 2,000 requests.
* Critical threshold $D_{\text{KS}} \le 0.098$ ($p$-value $\ge 0.05$).
* Error rate differential $\Delta E \le 0.005$ ($0.5\%$).
* If breached: **Instant automated rollback** triggered by Argo Rollouts controller within $4.2\text{s}$.

### Step 2.3: Promotion to 25% -> 50% -> 100%
```bash
# Verify AnalysisRun status
kubectl get analysisrun -n ndtm-system -l rollouts-pod-template-hash
# Promote to full deployment upon successful KS test
kubectl argo rollouts promote ndtm-backend -n ndtm-system
```

---

## 3. DAY-2 INCIDENT RESPONSE & PAGERDUTY RUNBOOKS

### Scenario A: High-Memory or Z3 SMT Solver Backpressure
* **Symptom:** `Alert: Z3SolverLatencyCritical` fired (P99 $> 25\text{ms}$).
* **Automated Action:** System drops Tier B Z3 SMT automatically and switches to Tier A Hungarian LNS fast baseline.
* **Manual Mitigation:**
  ```bash
  kubectl scale deployment ndtm-backend --replicas=12 -n ndtm-system
  ```

### Scenario B: RabbitMQ Outbox Relay Stagnation
* **Symptom:** `outbox_events` count $> 5,000$ uncommitted for $> 60\text{s}$.
* **Mitigation:**
  ```bash
  kubectl restart deployment ndtm-outbox-worker -n ndtm-system
  psql "$DATABASE_URL" -c "VACUUM (ANALYZE, VERBOSE) outbox_events;"
  ```
