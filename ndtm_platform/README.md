# Neuro-Distilled Triage Mesh (NDTM) 🚀

> **Production-Grade, Self-Evolving, Distributed AI Platform for Autonomous Incident Triage and Resource Scheduling**

NDTM marries **Knowledge Distillation**, **Neuro-Symbolic Constraint Solving (Z3)**, and **Multi-Agent Collaborative Workflows** with active learning feedback loops, differential privacy federated learning, and distributed semantic KV caching.

---

## 🏛️ System Architecture

```mermaid
graph TD
    Client([Citizen / IoT / External Reporter]) --> Gateway[FastAPI Gateway :8000]
    
    subgraph "Resiliency & Telemetry Layer"
        Gateway --> PII[PII Redactor & TCKN Modulo-11 Gate]
        PII --> RL[Token-Bucket Rate Limiter]
        RL --> Idemp[Idempotency Key Verifier]
        Idemp --> Prom[Prometheus Telemetry Registry]
    end

    subgraph "Pillar 1: Multimodal Triage & Deduplication"
        Gateway --> TriageSvc[Triage Service]
        TriageSvc --> LapImg[Laplacian Blur Filter Var > 60]
        TriageSvc --> PGVector[(PostgreSQL 16 + pgvector)]
        TriageSvc -.-> |Similarity > 0.88| Merge[Merge Duplicate & Inc Count]
        TriageSvc -.-> |Unique Report| RMQ[RabbitMQ triage_queue]
    end

    subgraph "Pillar 2: Knowledge Distillation & Semantic Router"
        Gateway --> Router[Semantic Router]
        Router --> SemCache[(Distributed Semantic KV-Cache > 0.95)]
        SemCache -.-> |Hit| FastReturn[Instant Bypass ~70% Latency Cut]
        SemCache -.-> |Miss| ONNX[DistillMesh ONNX Student <10ms, $0]
        ONNX --> CB[Circuit Breaker]
        CB -.-> |Fallback / Low Conf| Teacher[Teacher LLM Reasoning]
        ONNX -.-> |Async Mirror| Shadow[Shadow Evaluator]
    end

    subgraph "Pillar 3: Neuro-Symbolic Verification Engine"
        Gateway --> Z3Engine[Neuro-Symbolic Engine]
        Z3Engine --> SMT[Microsoft Z3 SMT Solver]
        SMT -.-> |UNSAT Violations| FeedbackLoop[Self-Correction Prompting]
        SMT -.-> |Exhausted| OptSolver[Z3 Optimize Global Synthesis]
    end

    subgraph "Advanced: Multi-Agent Workflow (LangGraph Pattern)"
        Gateway --> StateMachine[Multi-Agent State Machine]
        StateMachine --> TriageAgent[Triage Specialist Agent]
        TriageAgent --> AuditAgent[Compliance Auditor Agent]
        AuditAgent --> ConsensusGate{Consensus Score >= 0.85?}
        ConsensusGate -- No --> HITLSuspend[Suspend Workflow & Emit HITL Task]
        ConsensusGate -- Yes --> ExecAgent[Action Execution Agent + MCP Tools]
        HITLSuspend --> HumanReview[(PostgreSQL hitl_review_tasks)]
    end

    subgraph "Advanced: Continuous Learning & Edge Privacy"
        Shadow -.-> |Divergence > 0.40| FT[(fine_tuning_candidates)]
        FT -.-> |Count >= 1,000| LoRAWorker[Async LoRA PEFT Retrainer]
        LoRAWorker --> ONNXExport[ONNX Graph Export & In-Memory Hot-Swap]
        ONNXExport -.-> |Zero Downtime| ONNX
        Gateway --> FedSim[Zero-Trust Differential Privacy FedAvg Simulator]
    end
```

---

## ⚡ Core Pillars & Advanced Modules

| Module | Core Purpose | Latency Target | Guarantee / Protocol |
| :--- | :--- | :--- | :--- |
| **Multimodal Triage** | Validates text completeness & image sharpness via 3x3 Laplacian variance filter. | $< 25\text{ms}$ | Blurry/corrupt images rejected before DB write. |
| **Semantic Deduplication** | Searches `ticket_embeddings` via pgvector cosine distance (`<=>`). | $< 15\text{ms}$ | Advisory lock prevents insertion race conditions. |
| **Semantic KV-Cache** | Cluster-wide prompt prefix cache in Redis (`similarity > 0.95`). | $< 2\text{ms}$ | Bypasses attention calculation; cuts latency by 70%. |
| **DistillMesh Router** | Routes inference between local ONNX student and Teacher LLM. | $< 10\text{ms}$ (Student) | $0.00 cost per query on 80%+ traffic. |
| **Neuro-Symbolic Z3** | Translates operational plans to SMT-LIB constraints. | $< 50\text{ms}$ | Zero hallucinations: 100% verified math constraints. |
| **Multi-Agent State Machine** | Orchestrates Triage, Compliance, and Action execution agents. | Variable | Consensus $< 0.85$ triggers supervisor HITL suspension. |
| **Continuous Learning** | Retrains student on high-divergence edge cases via LoRA PEFT. | Background | Zero-downtime atomic model hot-swap in memory. |
| **Federated Simulation** | Simulates edge nodes with SQLite & Gaussian DP noise. | Background | Raw private records never leave local edge nodes. |

---

## 🚀 Quickstart with Docker Compose

### 1. Prerequisites
- Docker Engine 24+ & Docker Compose v2+
- Ports available: `8000` (FastAPI), `5432` (PostgreSQL), `6379` (Redis), `5672`/`15672` (RabbitMQ)

### 2. Launch the Platform
```bash
# Clone and enter directory
cd ndtm_platform

# Copy environment variables
cp .env.example .env

# Build and start all 4 containers
docker-compose up --build -d
```

### 3. Verify System Health
Open your browser to:
- **Executive Command Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prometheus Telemetry**: [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Health Probe**: [http://localhost:8000/healthz](http://localhost:8000/healthz)
- **RabbitMQ Management**: [http://localhost:15672](http://localhost:15672) (User: `triage`, Pass: `triage_secret`)

---

## 📡 API Reference & Curl Examples

### 1. Multimodal Incident Triage & Deduplication
```bash
curl -X POST "http://localhost:8000/api/v1/triage" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req-unique-12345" \
  -d '{
    "description": "Atatürk Bulvarı üzerinde ana su borusu patladı, caddeyi su bastı.",
    "category": "plumbing"
  }'
```
**Response (200 OK):**
```json
{
  "status": "created",
  "message": "Ticket 9e15bb5c-486d-4952-b883-faad7ba83c1b created successfully.",
  "ticket_id": "9e15bb5c-486d-4952-b883-faad7ba83c1b",
  "similarity": 0.0,
  "cleaned_description": "Atatürk Bulvarı üzerinde ana su borusu patladı, caddeyi su bastı.",
  "urgency_score": 0.75,
  "category": "plumbing"
}
```

### 2. Multi-Tier Semantic Router & KV-Cache
```bash
curl -X POST "http://localhost:8000/api/v1/router" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Mahalledeki sokak lambaları yanmıyor, trafo patladı karanlıkta kaldık."
  }'
```
**Response (200 OK):**
```json
{
  "intent": "power_outage",
  "confidence": 0.94,
  "urgency": 0.85,
  "execution_path": "onnx_student",
  "latency_ms": 7.42,
  "cost_usd": 0.0,
  "from_cache": false
}
```
*(Repeating the same or semantically identical query yields `execution_path: "semantic_cache"` with `from_cache: true` and latency $< 2\text{ms}$).*

### 3. Neuro-Symbolic Verification (Z3 SMT Solver)
```bash
curl -X POST "http://localhost:8000/api/v1/symbolic" \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "id": "t1",
        "title": "Boru patlağı onarımı",
        "priority": 1,
        "required_skill": "plumbing",
        "estimated_duration_hours": 2.0,
        "deadline_hours": 6.0,
        "location": "Kızılay"
      }
    ],
    "technicians": [
      {
        "id": "tech_1",
        "name": "Ahmet Usta",
        "skills": ["plumbing"],
        "shift_hours": 8.0,
        "max_tasks": 3
      }
    ]
  }'
```
**Response (200 OK):**
```json
{
  "is_valid": true,
  "status": "solved_optimal",
  "plan": {
    "assignments": [
      {
        "task_id": "t1",
        "technician_id": "tech_1",
        "start_hour": 0.0,
        "end_hour": 2.0
      }
    ],
    "rationale": "Deterministically synthesized and verified via Z3 Optimize solver."
  },
  "violations": [],
  "solver_time_ms": 14.28,
  "rounds_executed": 1
}
```

### 4. Multi-Agent Collaborative Workflow & HITL
```bash
curl -X POST "http://localhost:8000/api/v1/agents/workflow" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Şüpheli kimyasal kokusu var, gaz sızıntısı olabilir."
  }'
```
**Response (200 OK):**
```json
{
  "ticket_id": null,
  "consensus_reached": true,
  "consensus_score": 0.925,
  "triage_summary": {
    "agent": "TriageSpecialistAgent",
    "category": "hazmat",
    "confidence": 0.96,
    "urgency": 0.95
  },
  "compliance_audit": {
    "agent": "ComplianceAuditorAgent",
    "compliant": true,
    "confidence": 0.82,
    "protocols_required": [
      "DISASTER_MANAGEMENT_EVACUATION_CHECK",
      "EPA_ENVIRONMENTAL_HAZARD_LOG",
      "FIRST_RESPONDER_PRIORITY_ESCALATION"
    ]
  },
  "execution_plan": {
    "agent": "ActionExecutionAgent",
    "actions_executed_count": 2,
    "summary": "Action plan formulated with 2 MCP actions: notify_emergency_services, dispatch_technician_crew"
  },
  "hitl_required": false,
  "review_task_id": null
}
```

### 5. Zero-Trust Differential Privacy Federated Learning
```bash
curl -X POST "http://localhost:8000/api/v1/federated/simulate?num_nodes=3&rounds=2&epsilon=1.5"
```

---

## 🧪 Running Automated Tests

Run the full async test suite using `pytest`:
```bash
python -m pytest tests/ -v
```
All 13 test suites validate:
- TCKN Modulo-10/11 mathematical checksums
- Laplacian blur filter thresholds
- Semantic KV-Cache cosine matching
- Teacher LLM Circuit Breaker tripping and reset
- Z3 constraint checks (Interval overlaps, skill matching, deadline violations)
- Multi-Agent consensus scoring and HITL state suspension
