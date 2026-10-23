import asyncio
import json
import uuid
import numpy as np
from typing import Optional
import aio_pika
from core.config import settings
from core.logging_otel import logger, INCIDENT_INGEST_TOTAL, TRIAGE_LATENCY_HISTOGRAM
from infrastructure.database.connection import AsyncSessionLocal
from infrastructure.repositories.uow_repositories import UnitOfWork
from infrastructure.database.orm_models import IncidentOrm, IncidentClusterOrm, DispatchScheduleOrm
from application.middleware.pii_scrubber import PIIScrubber
from application.middleware.owasp_llm_firewall import OWASPLLMFirewall
from domain.services.onnx_runtime_engine import OnnxRuntimeEngine
from domain.services.pid_entropy_router import ModelRouter
from domain.services.text_encoder import encode_text_to_feature_vector
from domain.services.hawkes_process_engine import HawkesProcessEngine, HawkesHistoricalEvent
from domain.services.smt_pareto_dispatcher import SmtParetoDispatcher
from domain.value_objects import GeoCoordinates
from domain.events import IncidentIngestedEvent, ModelTriageDispatchedEvent


class RabbitMQTriageWorker:
    """Asynchronous RabbitMQ consumer executing the carrier-grade triage & dispatch pipeline."""

    def __init__(self):
        self.onnx_engine = OnnxRuntimeEngine()
        self.router = ModelRouter()
        self.hawkes = HawkesProcessEngine()
        self.dispatcher = SmtParetoDispatcher()
        self._is_running = False

    async def run(self) -> None:
        self._is_running = True
        logger.info("rabbitmq_triage_worker_connecting", url=settings.rabbitmq_url)

        connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        queue = await channel.declare_queue("ndtm.triage.requests", durable=True)
        logger.info("rabbitmq_triage_worker_listening", queue="ndtm.triage.requests")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._is_running:
                    break

                async with message.process(requeue=False):
                    try:
                        raw_body = json.loads(message.body.decode("utf-8"))
                        await self.process_incident(raw_body)
                    except Exception as e:
                        logger.error("triage_worker_failed_to_process", error=str(e))

    async def process_incident(self, payload: dict) -> None:
        """Executes full pipeline for single incident report."""
        import time
        start_time = time.time()

        raw_desc = payload.get("description", "")
        urgency = payload.get("urgency", "MEDIUM")
        lat = float(payload.get("latitude", 41.0082))
        lon = float(payload.get("longitude", 28.9784))
        title = payload.get("title", "Operational Incident")
        modality = payload.get("modality", "TEXT_ONLY")
        source = payload.get("source_protocol", "API_REST")

        INCIDENT_INGEST_TOTAL.labels(source_protocol=source, urgency=urgency).inc()

        # 1. PII Scrubbing
        scrubbed_desc, redaction_count = PIIScrubber.scrub_text(raw_desc)

        # 2. OWASP LLM Firewall
        has_threat, threat_reasons = OWASPLLMFirewall.inspect(scrubbed_desc)
        if has_threat:
            logger.warning("threat_detected_in_incident_payload", threats=threat_reasons)
            urgency = "CRITICAL"

        # 3. Feature Vector & Model Inference
        feature_vec = encode_text_to_feature_vector(scrubbed_desc, dim=384)
        pred_cat, conf, probs, embedding = self.onnx_engine.infer_triage(feature_vec)

        # 4. Routing Decision (PID Entropy + OOD)
        route_decision, entropy, ood_dist, dyn_thresh = self.router.evaluate_route(probs, embedding, urgency)

        # 5. Spatio-Temporal Hawkes Aftershock Check
        coord = GeoCoordinates(latitude=lat, longitude=lon)
        # Check active clusters in DB
        async with AsyncSessionLocal() as session:
            async with UnitOfWork(session) as uow:
                matched_cluster = await uow.clusters.find_matching_cluster(lon, lat)
                cluster_id = None

                if matched_cluster:
                    cluster_id = matched_cluster.id
                    matched_cluster.incident_count += 1
                else:
                    # Create new Hawkes cluster seed
                    new_cluster_id = uuid.uuid4()
                    cluster_orm = IncidentClusterOrm(
                        id=new_cluster_id,
                        centroid=f"SRID=4326;POINT({lon:.7f} {lat:.7f})",
                        radius_meters=500.0,
                        cluster_urgency=urgency,
                        incident_count=1,
                    )
                    await uow.clusters.create(cluster_orm)
                    cluster_id = new_cluster_id

                # Create Incident in DB
                inc_id = uuid.uuid4()
                inc_orm = IncidentOrm(
                    id=inc_id,
                    cluster_id=cluster_id,
                    title=title,
                    description_scrubbed=scrubbed_desc,
                    urgency=urgency,
                    category=pred_cat,
                    modality=modality,
                    source_protocol=source,
                    location=f"SRID=4326;POINT({lon:.7f} {lat:.7f})",
                    embedding=embedding.tolist(),
                    triage_state="TRIAGED" if route_decision != "HITL_REQUIRED" else "PENDING_HITL",
                    triage_decision=pred_cat,
                    triage_confidence=conf,
                    metadata_json={
                        "entropy": entropy,
                        "ood_dist": ood_dist,
                        "route_decision": route_decision,
                        "redactions": redaction_count,
                    },
                )
                await uow.incidents.create(inc_orm)

                # Record Domain Events
                ingest_ev = IncidentIngestedEvent(
                    aggregate_type="Incident",
                    aggregate_id=inc_id,
                    event_type="IncidentIngested",
                    payload={"id": str(inc_id), "category": pred_cat, "urgency": urgency},
                ).sign()

                await uow.outbox.enqueue(
                    aggregate_type="Incident",
                    aggregate_id=inc_id,
                    event_type="IncidentIngested",
                    payload=ingest_ev.payload,
                    routing_key="incident.event.ingested",
                )

        duration = time.time() - start_time
        TRIAGE_LATENCY_HISTOGRAM.labels(route_decision=route_decision, model_tier="student").observe(duration)
        logger.info(
            "incident_pipeline_processed_successfully",
            incident_id=str(inc_id),
            category=pred_cat,
            confidence=conf,
            route=route_decision,
            latency=duration,
        )

    def stop(self) -> None:
        self._is_running = False


if __name__ == "__main__":
    worker = RabbitMQTriageWorker()
    try:
        asyncio.run(worker.run())
    except (KeyboardInterrupt, SystemExit):
        worker.stop()
