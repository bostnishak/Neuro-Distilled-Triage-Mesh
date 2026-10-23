# Enterprise Production Hardening Guide
## Neuro-Distilled Triage Mesh

This guide documents the enterprise reliability, observability, security, and fault tolerance architecture implemented for production deployments.

---

## 1. Observability, Telemetry & Distributed Tracing

### Prometheus Metrics Exposition (`/metrics`)
The system exposes standard Prometheus metrics at `GET /metrics` for continuous scraping via Prometheus, OpenTelemetry Collector, or Datadog Agent.

```bash
curl -s http://localhost:8000/metrics | grep mesh_
```

#### Metrics Catalog
| Metric Name | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `mesh_http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Total HTTP requests processed |
| `mesh_http_request_duration_seconds` | Histogram | `method`, `endpoint` | End-to-end HTTP request latency |
| `mesh_onnx_inference_duration_seconds` | Histogram | `model_name` | Isolated execution time of the INT8 ONNX student model |
| `mesh_router_inferences_total` | Counter | `route`, `intent` | Breakdown of inferences routed to `student`, `teacher`, or `heuristic` |
| `mesh_router_cache_hits_total` | Counter | `status` | Cache hits/misses for semantic routing decisions |
| `mesh_circuit_breaker_state` | Gauge | `service` | Circuit Breaker state: `0` = Closed, `1` = Half-Open, `2` = Open |
| `mesh_shadow_divergence_score` | Histogram | None | Divergence score between Student and Teacher LLM ($0.0 - 1.0$) |
| `mesh_rabbitmq_queue_depth` | Gauge | `queue_name` | Pending message depth in RabbitMQ queues |

### Sample Prometheus Scrape Configuration
```yaml
scrape_configs:
  - job_name: 'triage-mesh'
    scrape_interval: 10s
    metrics_path: '/metrics'
    static_configs:
      - targets: ['api:8000']
```

### Distributed Tracing & Correlation IDs
Every request is tagged with an `X-Request-ID` UUID header. If the client omits it, the gateway automatically generates one. The ID is bound via Python `contextvars` and propagated across:
* Outbound HTTP responses (`X-Request-ID` header)
* JSON-formatted stdout logs (`request_id` field)
* RabbitMQ message headers (`x-request-id`)
* Database audit records in `audit_logs` and `scheduling_runs`

---

## 2. Advanced Resiliency & Fault Tolerance

### Circuit Breaker for Upstream LLM Calls
When using external Teacher LLM APIs (e.g. OpenAI, vLLM, Azure OpenAI), rate limits (`429`) or network timeouts can starve FastAPI worker threads.

```text
[CLOSED] --(3 consecutive failures)--> [OPEN] --(30s recovery timeout)--> [HALF_OPEN]
   ^                                                                           │
   └───────────────────────────(1 probe success)───────────────────────────────┘
```

* **Behavior**:
  - `failure_threshold`: 3 consecutive failures.
  - `recovery_timeout`: 30.0 seconds.
  - While `OPEN`: External calls fail fast immediately; the Semantic Router seamlessly falls back to the local ONNX student model or keyword heuristic without throwing 5xx errors to the client.

### Idempotency Middleware (`Idempotency-Key`)
To eliminate duplicate ticket creation from client retries during transient network disconnections, all mutating endpoints support idempotency keys:

```bash
curl -X POST "http://localhost:8000/api/v1/triage/report" \
  -H "Idempotency-Key: a5f1b2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c" \
  -F "description=Severe water pipe burst on Elm Street." \
  -F "latitude=41.0082" \
  -F "longitude=28.9784"
```

1. **Fingerprint Verification**: Computes a SHA-256 hash of the request body and endpoint.
2. **Atomic Storage**: Stored in PostgreSQL `idempotency_keys` table with a 24-hour TTL.
3. **Replay Protection**: Identical keys return cached HTTP status codes and payloads directly (`X-Cache-Lookup: HIT-IDEMPOTENT`). Divergent payloads with the same key return `422 Unprocessable Entity`.

### RabbitMQ Dead Letter Queue (DLQ) & Alerting
* Tasks in `triage_queue` retry up to 3 times via `triage_retry` (10s TTL redelivery).
* Upon exceeding `triage_max_retries`:
  1. The poison message is published to `triage_dlq`.
  2. A critical structured SRE alert log is generated:
     ```json
     {"alert": "RABBITMQ_DLQ_POISON_MESSAGE", "severity": "CRITICAL", "ticket_id": "...", "attempts": 3}
     ```

---

## 3. Security, PII Redaction & Rate Limiting

### Automated PII Redaction
Before any user description or address reaches `pgvector` embeddings or database storage, the pipeline runs deterministic regex and checksum filters:

* **Turkish TC Kimlik No (TCKN)**: 11-digit numbers are validated against the official algorithmic checksum formula. Valid IDs are masked to `[MASKED_TCKN]` to eliminate GDPR / KVKK non-compliance while preventing false positives on general numbers.
* **Phone Numbers**: Turkish mobile (`05xx`, `+90 5xx`) and international formats $\rightarrow$ `[MASKED_PHONE]`.
* **Email Addresses**: RFC 5322 regex matching $\rightarrow$ `[MASKED_EMAIL]`.
* **Financial Identifiers**: IBANs (`TR` + 24 digits) and credit card numbers $\rightarrow$ `[MASKED_IBAN]` / `[MASKED_CARD]`.

### Prompt Injection & Delimiter Defense
`sanitize_input_text` strips non-printable control characters and neutralizes LLM delimiter triggers such as:
* `<|im_start|>`, `<|im_end|>`
* `[INST]`, `[/INST]`
* `system:`, `Ignore previous instructions`
* Delimiters are replaced with `[FILTERED_PROMPT_DELIMITER]` before passing to models.

### Token-Bucket Rate Limiter
* Configurable token bucket algorithm per client IP.
* Default: **180 requests/minute** with a burst allowance of **30 tokens**.
* Exceeding limits returns `429 Too Many Requests` with a standard `Retry-After: 2` header.

---

## 4. Continuous Model Evaluation & Shadow Testing

When the Semantic Router accepts a prediction from the fast ONNX student model, an asynchronous background task mirrors the request to the Teacher LLM to compute a **semantic divergence score**:

$$\text{Divergence Score} = 0.65 \times (0 \text{ if match else } 1) + 0.35 \times \min(|\text{Urgency}_{\text{student}} - \text{Urgency}_{\text{teacher}}|, 1.0)$$

* Results are persisted in the `shadow_evaluations` table for automated drift monitoring.
* High divergence ($>0.50$) triggers structured warnings in logs.
* Histogram metrics are pushed to `mesh_shadow_divergence_score`.

---

## 5. Automated Deep Health Check (`/healthz`)

Query `GET /healthz` for comprehensive infrastructure verification:

```bash
curl -s http://localhost:8000/healthz | jq
```

**Response (HTTP 200 OK):**
```json
{
  "status": "healthy",
  "components": {
    "database": {
      "connected": true,
      "pgvector_ready": true
    },
    "rabbitmq": {
      "connected": true
    },
    "onnx_student": {
      "loaded": true,
      "model_name": "distillmesh-student-int8"
    },
    "circuit_breaker": {
      "teacher_llm_state": "closed"
    }
  }
}
```

If PostgreSQL, `pgvector`, or RabbitMQ are unreachable, the endpoint returns `503 Service Unavailable` with specific error diagnostics.

---

## 6. Running Automated Tests

Run the full hardened test suite:

```bash
pytest -v
```

### Test Coverage Highlights:
1. `tests/test_resiliency_and_security.py`:
   - Algorithmic TCKN, phone, email, and IBAN masking.
   - Prompt injection delimiter sanitization.
   - Circuit Breaker transitions (`CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF_OPEN` $\rightarrow$ `CLOSED`).
   - Token bucket capacity and refill rate limits.
2. `tests/test_shadow_evaluator.py`:
   - Model alignment vs divergence score calculations.
3. `tests/test_symbolic_engine.py`:
   - Z3 Theorem Prover constraint verification & optimal schedule synthesis.
4. `tests/test_router.py`:
   - Confidence thresholding, top-2 class margin gating, and prototype OOD escalation.
5. `tests/test_triage_dedup.py`:
   - Discrete Laplacian variance blur detection & exposure limits.
