# Neuro-Distilled Triage Mesh

[![Architecture](https://img.shields.io/badge/Architecture-Neuro--Symbolic-indigo.svg)](#)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Z3](https://img.shields.io/badge/Solver-Microsoft%20Z3-ff69b4.svg)](https://github.com/Z3Prover/z3)
[![ONNX](https://img.shields.io/badge/Inference-ONNX%20INT8-blueviolet.svg)](https://onnxruntime.ai/)
[![PostgreSQL](https://img.shields.io/badge/VectorDB-PostgreSQL%20%2B%20pgvector-336791.svg)](https://github.com/pgvector/pgvector)
[![RabbitMQ](https://img.shields.io/badge/Queue-RabbitMQ%203.13-ff6600.svg)](https://www.rabbitmq.com/)

An enterprise-grade, production-ready system fusing **Knowledge Distillation**, **Active Multimodal Semantic Deduplication**, and **Deterministic Neuro-Symbolic Verification (Z3 Theorem Prover)** for critical infrastructure and incident response.

---

## Architecture Overview

```mermaid
flowchart TD
    Citizen([Citizen / Incident Reporter]) -->|Photo + Text + GPS| Gateway[Module 1: Multimodal Triage Gateway]

    subgraph Module 1: Active Triage Gate
        Gateway --> ImageCheck{Deterministic Image Gate & VLM}
        ImageCheck -->|Blurry / Incomplete| RejectPrompt[Interactive Clarification Prompt]
        ImageCheck -->|Valid| Embedder[Multilingual Sentence Embedder]
        Embedder --> VectorSearch{pgvector HNSW Cosine Search}
        VectorSearch -->|Similarity > 0.88| MergeTicket[(Merge into Active Master Ticket)]
        VectorSearch -->|Unique| Commit[(PostgreSQL: Ticket + Outbox)]
    end

    Commit --> OutboxRelay[Transactional Outbox Relay]
    OutboxRelay --> Broker[(RabbitMQ triage_queue)]

    subgraph Module 2: DistillMesh Semantic Router
        Broker --> Worker[Async Triage Worker]
        Worker --> Router{DistillMesh Semantic Router}
        Router -->|80% Standard / In-Distribution| ONNXStudent[5ms INT8 ONNX Student Model: $0.00]
        Router -->|20% Ambiguous / OOD| TeacherLLM[Teacher LLM Gateway]
        ONNXStudent --> UpdateDB[(Update Ticket Metadata & Entities)]
        TeacherLLM --> UpdateDB
    end

    subgraph Module 3: Neuro-Symbolic Verification Engine
        Dispatch[Resource Allocator / Dispatcher] --> Engine[Neuro-Symbolic Engine]
        Engine --> LLMPlan[LLM Synthesizer]
        LLMPlan --> Z3Verifier[Microsoft Z3 Theorem Prover]
        Z3Verifier -->|Violation Found| MathFeedback[Counter-Example Conflict Proof]
        MathFeedback -->|Self-Correction Loop| LLMPlan
        Z3Verifier -->|SAT / Verified| ExecutionPlan([100% Zero-Hallucination Execution Plan])
    end
```

---

## Three Technical Pillars

### 1. Active Multimodal Triage & Semantic Deduplication
* **Quality & Completeness Gate**: Pre-validates reports *before* database commit. Rejects blurry photos (discrete Laplacian variance thresholding), improper exposure, and missing location context.
* **Vector Deduplication (`pgvector`)**: Uses cosine similarity against active tickets within a geographic bounding box and category cluster. Matches with similarity $\ge 0.88$ are automatically merged into the master incident to prevent duplicate field dispatches.
* **Transactional Outbox Pattern**: Persists the ticket and its dispatch event in the same ACID database transaction, preventing dual-write inconsistency between Postgres and RabbitMQ.

### 2. DistillMesh: Knowledge Distillation & Model Routing
* **Multi-Task Student Model**: Distills intent classification, urgency score regression, and token-level BIO named entity recognition into an ultra-fast INT8 quantized ONNX graph.
* **Semantic Router**: Evaluates incoming reports with multi-criteria gating:
  * Softmax confidence threshold ($\ge 0.80$)
  * Top-2 class margin threshold ($\ge 0.15$)
  * Calibrated centroid prototype cosine distance (Out-Of-Distribution detection)
* **Economics & Latency**: Standard requests (~80%) are served by the local CPU ONNX runtime in **$<5\text{ms}$ at $\$0.00$ incremental cost**. Escalates ambiguous/OOD queries to the Teacher LLM.

### 3. Neuro-Symbolic Verification Engine
* **The Problem**: Pure LLMs hallucinate impossible schedules—assigning technicians to two places at once, ignoring shift hour limits, or assigning technicians without the required certifications.
* **The Neuro-Symbolic Solution**: Couples natural language planning with the **Microsoft Z3 Theorem Prover**.
* **Self-Correction Loop**: When Z3 proves a mathematical conflict (e.g., overlapping intervals $[1.0, 2.5] \cap [2.0, 3.5] \neq \emptyset$), it extracts a counter-example proof. The LLM receives this formal proof and self-repairs its proposal until verified SAT.
* **Guaranteed SMT Fallback**: If an LLM is unreachable or fails repeatedly, Z3's SMT optimizer synthesizes the provably optimal schedule directly.

---

## Directory Layout

```text
.
├── docker-compose.yml          # PostgreSQL 16 + pgvector, RabbitMQ 3.13, API, Worker
├── Dockerfile                  # Non-root, slim Python 3.11 with CPU-optimized Torch/ONNX
├── requirements.txt            # Pinned runtime dependencies
├── pyproject.toml              # Project metadata & tooling config
├── .env.example                # Documented configuration template
├── main.py                     # FastAPI application & interactive dashboard
│
├── database/
│   └── schema.sql              # HNSW index, tickets, reports, outbox, audit logs
│
├── core/
│   ├── config.py               # Pydantic v2 typed settings
│   ├── logging_config.py       # JSON structured logging with request correlation
│   ├── taxonomy.py             # Shared domain labels and priority mapping
│   ├── database.py             # asyncpg connection pool with vector/JSON codecs
│   ├── broker.py               # aio-pika client with DLQ & retry topology
│   ├── outbox.py               # Transactional outbox relay
│   ├── llm.py                  # Resilient OpenAI-compatible client with retries
│   └── embeddings.py           # Thread-offloaded SentenceTransformer service
│
├── services/
│   ├── triage_service.py       # Active validation & pgvector deduplication
│   ├── router_service.py       # DistillMesh semantic router & ONNX engine
│   └── symbolic_engine.py      # Z3 Theorem Prover verifier & self-correction loop
│
├── distillation/
│   ├── pipeline.py             # Teacher generation, critic filter, student training & export
│   └── bootstrap_student.py    # Instant zero-config student model generator
│
├── workers/
│   └── triage_worker.py        # RabbitMQ background worker
│
└── tests/
    ├── test_symbolic_engine.py # Z3 overlap, skill, shift hours, and optimal synthesis tests
    ├── test_triage_dedup.py    # Sharp vs blurry image gate tests
    └── test_router.py          # Routing decision & OOD trigger tests
```

---

## Quickstart

### Option A: Complete Docker Topology (Recommended)

Start PostgreSQL (with `pgvector`), RabbitMQ, FastAPI gateway, and the background worker with a single command:

```bash
# 1. Clone & copy environment variables
cp .env.example .env

# 2. Launch all services
docker compose up --build -d

# 3. Verify health
docker compose ps
curl http://localhost:8000/health
```

Access the interfaces:
* **Interactive Live Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
* **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **RabbitMQ Management Console**: [http://localhost:15672](http://localhost:15672) (`user: triage`, `pass: triage_secret`)

---

### Option B: Local Development Setup

#### 1. Setup Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

#### 2. Start Infrastructure Containers
```bash
docker compose up -d postgres rabbitmq
```

#### 3. Bootstrap Initial Student Model & Prototypes
Generate an initial INT8 ONNX student model and prototype embeddings in `models/student/`:
```bash
python -m distillation.bootstrap_student
```

#### 4. Run the API Gateway & Worker
In terminal 1:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

In terminal 2:
```bash
python -m workers.triage_worker
```

---

## Verification & API Usage

### 1. Submit a Report (Multimodal Triage Gateway)

```bash
curl -X POST "http://localhost:8000/api/v1/triage/report" \
  -F "description=Severe water main leak flooding the intersection of Pine Street and 5th Ave." \
  -F "latitude=37.7749" \
  -F "longitude=-122.4194" \
  -F "address=Pine St & 5th Ave" \
  -F "category=water_leak" \
  -F "image=@tests/fixtures/sample_leak.jpg"
```

**Response (Unique Ticket Created & Queued):**
```json
{
  "status": "queued",
  "message": "Your report was received as ticket 4a3e8770-... and is being triaged.",
  "ticket_id": "4a3e8770-3882-4467-bc13-fdf49ec604ce",
  "report_id": "992144d1-43ee-4f36-9286-6e5461c28c8c",
  "questions": [],
  "image_quality": {
    "valid": true,
    "format": "JPEG",
    "width": 1280,
    "height": 720,
    "blur_score": 284.1,
    "brightness": 142.3,
    "issues": []
  }
}
```

**Submitting a Duplicate Report (Automated Deduplication):**
```bash
curl -X POST "http://localhost:8000/api/v1/triage/report" \
  -F "description=Flooding from broken water pipe on Pine St near 5th." \
  -F "latitude=37.7750" \
  -F "longitude=-122.4195"
```
**Response (Merged):**
```json
{
  "status": "merged_duplicate",
  "message": "Thanks! This issue is already being tracked as ticket 4a3e8770-... (2 reports, 93% match). We merged your report so crews see the added impact.",
  "ticket_id": "4a3e8770-3882-4467-bc13-fdf49ec604ce",
  "similarity": 0.9312
}
```

---

### 2. DistillMesh Semantic Inference

```bash
curl -X POST "http://localhost:8000/api/v1/router/infer" \
  -H "Content-Type: application/json" \
  -d '{"text": "Deep hazardous pothole on Elm Street causing flat tires."}'
```

**Response (Local ONNX Student - 4.1ms):**
```json
{
  "prediction": {
    "intent": "road_damage",
    "confidence": 0.9412,
    "urgency": 0.75,
    "priority": 2,
    "entities": [
      {"type": "HAZARD", "text": "Deep hazardous pothole"},
      {"type": "LOCATION", "text": "Elm Street"}
    ]
  },
  "route": "student",
  "model_name": "distillmesh-student-int8",
  "latency_ms": 4.12,
  "estimated_cost_usd": 0.0
}
```

---

### 3. Neuro-Symbolic Verification Engine (Z3)

Request an emergency dispatch assignment:

```bash
curl -X POST "http://localhost:8000/api/v1/symbolic/schedule" \
  -H "Content-Type: application/json" \
  -d '{
    "technicians": [
      {"id": "tech-1", "name": "Alice Vance", "skills": ["electrical"], "shift_hours": 8.0, "max_tasks": 3},
      {"id": "tech-2", "name": "Bob Martinez", "skills": ["plumbing"], "shift_hours": 8.0, "max_tasks": 3}
    ],
    "tasks": [
      {"id": "task-101", "title": "Sparking Transformer", "priority": 1, "required_skill": "electrical", "estimated_duration_hours": 2.5, "deadline_hours": 4.0, "location": "Main St"},
      {"id": "task-102", "title": "Water Main Burst", "priority": 1, "required_skill": "plumbing", "estimated_duration_hours": 3.0, "deadline_hours": 5.0, "location": "4th Ave"}
    ]
  }'
```

**Response (Z3 Mathematical SAT Verification):**
```json
{
  "is_valid": true,
  "status": "solved_optimal",
  "solver_time_ms": 8.42,
  "rounds_executed": 0,
  "plan": {
    "rationale": "Mathematically synthesized and verified via Z3 Theorem Prover optimization.",
    "assignments": [
      {"task_id": "task-101", "technician_id": "tech-1", "start_hour": 0.0, "end_hour": 2.5},
      {"task_id": "task-102", "technician_id": "tech-2", "start_hour": 0.0, "end_hour": 3.0}
    ]
  }
}
```

---

## Running the Automated Test Suite

Run the full pytest suite:

```bash
pytest -v
```

Tests cover:
* **Z3 Theorem Prover verification**: Time overlaps, skill mismatch, shift capacity limits, and unassigned critical tasks.
* **Triage Image Gate**: Sharp vs blurry images, resolution limits, and dark/overexposed frames.
* **DistillMesh Routing Policy**: Softmax confidence, margin thresholding, and prototype OOD detection.

---

## Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://triage:...@localhost:5432/triage` | PostgreSQL with `pgvector` connection string |
| `RABBITMQ_URL` | `amqp://triage:...@localhost:5672/` | RabbitMQ connection string |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-base` | Sentence transformer model |
| `EMBEDDING_DIM` | `768` | Dimension matching `vector(N)` in schema |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.88` | Cosine similarity threshold for deduplication |
| `ROUTER_CONFIDENCE_THRESHOLD` | `0.80` | Minimum student confidence before teacher escalation |
| `ROUTER_MARGIN_THRESHOLD` | `0.15` | Minimum top-2 probability margin |
| `Z3_TIMEOUT_MS` | `10000` | Maximum solver duration in milliseconds |
| `LLM_ENABLED` | `false` | Enable Teacher LLM gateway |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible API (OpenAI, vLLM, Ollama) |
