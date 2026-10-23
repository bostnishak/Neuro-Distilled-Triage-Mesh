import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.config import settings
from core.exceptions import (
    NDTMKernelException,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ConflictError,
    GCRAExceededException,
    IdempotencyConflictException,
    CircuitBreakerOpenException,
    SmtUnsatException,
)
from core.logging_otel import logger
from infrastructure.database.connection import check_database_health
from infrastructure.messaging.transactional_outbox_relay import TransactionalOutboxRelay
from sdk.plugin_registry import PluginRegistry
from application.mcp_server import MCPServer
from domain.services.onnx_runtime_engine import ModelUnavailableError
from core.preflight_warmup_gate import PREFLIGHT_GATE

# Routers
from presentation.api.v1.auth import router as auth_router
from presentation.api.v1.incidents import router as incidents_router
from presentation.api.v1.clusters import router as clusters_router
from presentation.api.v1.dispatch import router as dispatch_router
from presentation.api.v1.causal import router as causal_router
from presentation.api.v1.hitl import router as hitl_router
from presentation.api.v1.audit import router as audit_router
from presentation.api.v1.telemetry_ws import router as telemetry_ws_router
from presentation.api.v3_production_sre import router as sre_v3_router, public_router as sre_public_router
from presentation.api.v3_multiregion_crdt import router as crdt_v3_router
from presentation.api.dependencies import get_current_user, require_role

outbox_relay = TransactionalOutboxRelay()
mcp_server = MCPServer()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and graceful shutdown hooks."""
    logger.info("ndtm_application_startup_initiated", service=settings.SERVICE_NAME)

    # 1. Discover plugins dynamically
    PluginRegistry.discover_plugins("plugins")

    # 2. Run pre-flight warmup to guarantee P99 < 15ms
    PREFLIGHT_GATE.run_preflight_warmup()

    # 3. Launch background transactional outbox publisher
    relay_task = asyncio.create_task(outbox_relay.run())

    yield

    # Graceful shutdown
    logger.info("ndtm_application_shutdown_initiated")
    await outbox_relay.stop()
    relay_task.cancel()
    try:
        await relay_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Neuro-Distilled Triage Mesh (NDTM-9000)",
    description="Sovereign AI & Systems Operating Kernel for Multimodal Triage, Formal MaxSMT Dispatch, and Causal Countermeasures",
    version="2.0.0",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.exception_handler(ModelUnavailableError)
async def model_unavailable_handler(_: Request, exc: ModelUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
    )


# Exception Handlers
@app.exception_handler(GCRAExceededException)
async def gcra_exception_handler(_: Request, exc: GCRAExceededException) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": "GCRA_RATE_LIMIT_EXCEEDED", "message": exc.message, "details": exc.details},
        headers={"Retry-After": str(max(1, exc.retry_after_ms // 1000))},
    )


@app.exception_handler(IdempotencyConflictException)
async def idempotency_exception_handler(_: Request, exc: IdempotencyConflictException) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"error": "IDEMPOTENCY_CONFLICT", "message": exc.message},
    )


@app.exception_handler(CircuitBreakerOpenException)
async def circuit_breaker_exception_handler(_: Request, exc: CircuitBreakerOpenException) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "CIRCUIT_BREAKER_OPEN", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(SmtUnsatException)
async def smt_unsat_exception_handler(_: Request, exc: SmtUnsatException) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "SMT_CONSTRAINTS_UNSATISFIABLE", "message": exc.message, "details": exc.details},
    )


@app.exception_handler(NotFoundError)
async def not_found_exception_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "NOT_FOUND", "message": exc.message},
    )


@app.exception_handler(AuthorizationError)
async def authz_exception_handler(_: Request, exc: AuthorizationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"error": "FORBIDDEN", "message": exc.message},
    )


@app.exception_handler(AuthenticationError)
async def authn_exception_handler(_: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "UNAUTHORIZED", "message": exc.message},
    )


@app.exception_handler(ModelUnavailableError)
async def model_unavailable_exception_handler(_: Request, exc: ModelUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
    )


# System Health & Metrics Endpoints
@app.get("/health", tags=["Platform Observability"])
async def health_check(response: Response) -> Dict[str, Any]:
    """Combined health probe returning 503 when critical downstream dependencies are disconnected."""
    db_ok = await check_database_health()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "HEALTHY" if db_ok else "DEGRADED",
        "service": settings.SERVICE_NAME,
        "database_connected": db_ok,
    }


@app.get("/livez", tags=["Platform Observability"])
def liveness_probe() -> Dict[str, str]:
    """Kubernetes liveness probe: indicates process is responsive."""
    return {"status": "ALIVE"}


@app.get("/readyz", tags=["Platform Observability"])
async def readiness_probe(response: Response) -> Dict[str, Any]:
    """Kubernetes readiness probe: indicates application is ready to accept traffic."""
    db_ok = await check_database_health()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "NOT_READY", "reason": "database_unavailable"}
    return {"status": "READY"}


@app.get("/metrics", tags=["Platform Observability"])
def prometheus_metrics() -> Response:
    """Exposes real-time Prometheus scrape metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# MCP JSON-RPC Gateway Endpoint
@app.post("/mcp/rpc", tags=["Model Context Protocol Gateway"])
async def mcp_rpc_gateway(request: Request, _user=Depends(get_current_user)) -> Response:
    """Handles JSON-RPC 2.0 requests from authenticated MCP clients."""
    payload = await request.json()
    rpc_response = await mcp_server.handle_json_rpc(payload)
    return JSONResponse(content=rpc_response)


# Mount API v1 Routers
prefix = settings.API_V1_PREFIX
app.include_router(auth_router, prefix=prefix)
app.include_router(incidents_router, prefix=prefix)
app.include_router(clusters_router, prefix=prefix)
app.include_router(dispatch_router, prefix=prefix)
app.include_router(causal_router, prefix=prefix)
app.include_router(hitl_router, prefix=prefix)
app.include_router(audit_router, prefix=prefix)
app.include_router(telemetry_ws_router, prefix=prefix)

# Mount API v3 Production & SRE Routers (authenticated; only /readiness is public)
app.include_router(sre_public_router, prefix="/api")
app.include_router(sre_v3_router, prefix="/api", dependencies=[Depends(require_role("ADMIN"))])
app.include_router(crdt_v3_router, prefix="/api", dependencies=[Depends(require_role("ADMIN"))])
