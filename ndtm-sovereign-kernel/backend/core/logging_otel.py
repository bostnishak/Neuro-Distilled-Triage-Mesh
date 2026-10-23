import logging
import sys
from typing import Any, Dict
from core.config import settings

# Graceful OpenTelemetry Import
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

# Graceful Prometheus Metrics Import
try:
    from prometheus_client import Counter, Histogram, Gauge
    _HAS_PROM = True
except ImportError:
    _HAS_PROM = False

    class _DummyMetric:
        def __init__(self, *args: Any, **kwargs: Any):
            pass
        def labels(self, *args: Any, **kwargs: Any) -> "_DummyMetric":
            return self
        def inc(self, amount: float = 1) -> None:
            pass
        def observe(self, amount: float) -> None:
            pass
        def set(self, val: float) -> None:
            pass

    Counter = Histogram = Gauge = _DummyMetric  # type: ignore

# Setup OpenTelemetry Resource & Tracer if available
if _HAS_OTEL:
    resource = Resource.create({"service.name": settings.SERVICE_NAME, "environment": settings.ENVIRONMENT})
    trace_provider = TracerProvider(resource=resource)
    if settings.DEBUG:
        trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(trace_provider)
    tracer = trace.get_tracer(settings.SERVICE_NAME)
else:
    class _DummyTracer:
        def start_as_current_span(self, name: str) -> Any:
            from contextlib import nullcontext
            return nullcontext()
    tracer = _DummyTracer()  # type: ignore

# Prometheus Metrics Definitions
INCIDENT_INGEST_TOTAL = Counter(
    "ndtm_incident_ingest_total",
    "Total raw incident reports ingested",
    ["source_protocol", "urgency"],
)

TRIAGE_LATENCY_HISTOGRAM = Histogram(
    "ndtm_triage_latency_seconds",
    "End-to-end triage latency in seconds",
    ["route_decision", "model_tier"],
)

SMT_SOLVER_DURATION = Histogram(
    "ndtm_smt_solver_seconds",
    "Time taken for Z3 MaxSMT Pareto dispatch optimization",
    ["status"],
)

HAWKES_CLUSTER_GAUGE = Gauge(
    "ndtm_hawkes_active_clusters",
    "Number of currently active spatial-temporal Hawkes aftershock clusters",
)

CIRCUIT_BREAKER_STATE = Gauge(
    "ndtm_circuit_breaker_state",
    "Circuit breaker state: 0=CLOSED, 1=HALF_OPEN, 2=OPEN",
    ["service_name"],
)

SHM_SLOT_UTILIZATION = Gauge(
    "ndtm_shm_slot_utilization",
    "Active occupied slots in C++ zero-copy shared memory arena",
)

# Structlog Setup
try:
    import structlog
    def _add_opentelemetry_context(_: Any, __: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        if _HAS_OTEL:
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                span_ctx = current_span.get_span_context()
                if span_ctx.is_valid:
                    event_dict["trace_id"] = f"{span_ctx.trace_id:032x}"
                    event_dict["span_id"] = f"{span_ctx.span_id:016x}"
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_opentelemetry_context,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger()
except ImportError:
    logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO, format="%(message)s")
    logger = logging.getLogger("ndtm")  # type: ignore
