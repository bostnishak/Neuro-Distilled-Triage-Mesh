"""Main application entrypoint for Neuro-Distilled Triage Mesh (NDTM) Enterprise."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from backend.api import (
    v1_auth,
    v1_router,
    v1_scheduler,
    v1_system,
    v1_triage,
    v2_causal_twin,
    v2_federated,
    v2_ledger_and_kernel,
    v2_mcp_and_hitl,
)
from backend.core.config import get_settings
from backend.core.logging import setup_enterprise_logging
from backend.db.session import close_database_connections, init_asyncpg_pool
from backend.middleware.idempotency import IdempotencyMiddleware
from backend.middleware.prompt_guard import PromptGuardMiddleware
from backend.middleware.rate_limit import RateLimitMiddleware
from backend.services.onnx_runtime_engine import ONNXRuntimeEngine
from backend.services.websocket_manager import ws_manager

setup_enterprise_logging("INFO")
logger = logging.getLogger("main")
settings = get_settings()

# Prometheus Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "mesh_http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "mesh_http_request_duration_seconds",
    "Latency of HTTP requests in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes async database pools and bootstraps INT8 ONNX student model."""
    logger.info("Initializing NDTM Enterprise Platform...")
    try:
        await init_asyncpg_pool()
    except Exception as exc:
        logger.warning("Could not establish immediate database pool (%s). Running with graceful fallback.", exc)

    # Ensure baseline INT8 ONNX model is compiled and dynamic quantizer has run
    try:
        onnx_engine = ONNXRuntimeEngine(settings.ONNX_STUDENT_MODEL_PATH)
        logger.info("ONNX Student Engine initialized: %s", onnx_engine.model_path)
    except Exception as exc:
        logger.warning("ONNX Engine initialization notice: %s", exc)

    logger.info("NDTM Enterprise Platform operational.")
    yield
    logger.info("Shutting down NDTM Enterprise Platform...")
    await close_database_connections()
    logger.info("Platform shutdown completed.")


app = FastAPI(
    title="Neuro-Distilled Triage Mesh (NDTM) — Enterprise Core",
    description="High-throughput, mathematically verified AI incident triage, model distillation, and resource scheduling platform.",
    version="2.0.0",
    lifespan=lifespan,
)

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. AppSec Prompt Injection Shield
app.add_middleware(PromptGuardMiddleware)

# 3. Sliding-Window Rate Limiter
app.add_middleware(RateLimitMiddleware)

# 4. Idempotency Key Middleware
app.add_middleware(IdempotencyMiddleware)

# Prometheus Telemetry Exposition Endpoint
@app.get("/metrics", tags=["Operations"])
async def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Real-Time WebSocket Telemetry Stream
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keepalive ping-pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.debug("WebSocket exception: %s", exc)
        ws_manager.disconnect(websocket)


# Mount Versioned API Routers (V1 Core)
api_v1_prefix = settings.API_V1_PREFIX
app.include_router(v1_auth.router, prefix=api_v1_prefix)
app.include_router(v1_triage.router, prefix=api_v1_prefix)
app.include_router(v1_router.router, prefix=api_v1_prefix)
app.include_router(v1_scheduler.router, prefix=api_v1_prefix)
app.include_router(v1_system.router, prefix=api_v1_prefix)

# Mount Versioned API Routers (V2 Frontier Expansion)
api_v2_prefix = settings.API_V2_PREFIX
app.include_router(v2_causal_twin.router, prefix=api_v2_prefix)
app.include_router(v2_mcp_and_hitl.router, prefix=api_v2_prefix)
app.include_router(v2_federated.router, prefix=api_v2_prefix)
app.include_router(v2_ledger_and_kernel.router, prefix=api_v2_prefix)


@app.get("/", tags=["Operations"])
async def root_status() -> dict[str, Any]:
    return {
        "platform": settings.PROJECT_NAME,
        "environment": settings.ENVIRONMENT,
        "status": "OPERATIONAL",
        "version": "2.0.0",
        "docs_url": "/docs",
    }
