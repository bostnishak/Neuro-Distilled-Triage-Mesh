"""Module: Multimodal Triage Service for NDTM.

Coordinates multimodal validation (text completeness, image quality / blur detection),
PII redaction, vector deduplication via pgvector, and database persistence.
"""
from __future__ import annotations

import base64
import hashlib
import io
import logging
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import numpy as np
from PIL import Image

from ndtm_platform.middleware.pii_redaction import PIIRedactor
from ndtm_platform.models.schemas import TriageOutcome, TriageReportRequest
from ndtm_platform.services.deduplication_service import SemanticDeduplicationService

logger = logging.getLogger("triage_service")

# Safety limits for image processing
Image.MAX_IMAGE_PIXELS = 40_000_000
MIN_LAPLACIAN_VARIANCE = 60.0  # Threshold below which an image is considered blurry
MIN_TEXT_WORDS = 3


def compute_laplacian_variance(pil_img: Image.Image) -> float:
    """Compute the variance of the 2D Laplacian operator to quantify image sharpness.

    Uses a 3x3 discrete Laplacian kernel over normalized grayscale pixel array.
    """
    gray = pil_img.convert("L")
    arr = np.array(gray, dtype=np.float32)

    if arr.shape[0] < 3 or arr.shape[1] < 3:
        return 0.0

    # 3x3 Laplacian filter kernel
    kernel = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
    # Simple valid 2D convolution using numpy slicing
    h, w = arr.shape
    conv = (
        arr[0 : h - 2, 1 : w - 1]
        + arr[2:h, 1 : w - 1]
        + arr[1 : h - 1, 0 : w - 2]
        + arr[1 : h - 1, 2:w]
        - 4.0 * arr[1 : h - 1, 1 : w - 1]
    )
    return float(np.var(conv))


class TriageService:
    """High-performance triage engine executing validation, masking, and deduplication."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        dedup_service: SemanticDeduplicationService,
        pii_redactor: PIIRedactor | None = None,
        rabbitmq_channel: Any = None,
    ) -> None:
        self.pool = pool
        self.dedup_service = dedup_service
        self.redactor = pii_redactor or PIIRedactor()
        self.rabbitmq_channel = rabbitmq_channel

    def validate_image_data(self, image_data_base64: str) -> tuple[bool, str, float]:
        """Validates image payload: format, resolution, and sharpness."""
        try:
            # Strip base64 header if present
            if "," in image_data_base64:
                image_data_base64 = image_data_base64.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_data_base64)
            with Image.open(io.BytesIO(raw_bytes)) as img:
                img.verify()

            # Reopen for pixel analysis after verify()
            with Image.open(io.BytesIO(raw_bytes)) as img:
                fmt = (img.format or "").upper()
                if fmt not in ("JPEG", "PNG", "WEBP"):
                    return False, f"Unsupported image format: {fmt}. Allowed: JPEG, PNG, WEBP.", 0.0

                w, h = img.size
                if w < 100 or h < 100:
                    return False, f"Image resolution too low ({w}x{h}). Minimum required is 100x100.", 0.0

                blur_score = compute_laplacian_variance(img)
                if blur_score < MIN_LAPLACIAN_VARIANCE:
                    return (
                        False,
                        f"Image is too blurry for diagnostic triage (sharpness score {blur_score:.1f} < {MIN_LAPLACIAN_VARIANCE}). Please upload a clear photo.",
                        blur_score,
                    )

                return True, "Image quality passed.", blur_score
        except Exception as exc:
            return False, f"Invalid or corrupted image data: {exc}", 0.0

    def estimate_urgency_and_category(self, text: str) -> tuple[float, str]:
        """Heuristic semantic assessment of urgency and category for initial triage."""
        lower = text.lower()

        # Category rules
        if any(w in lower for w in ("su", "boru", "patlak", "kanalizasyon", "tıkalı", "leak", "water", "pipe")):
            category = "plumbing"
        elif any(w in lower for w in ("elektrik", "kablo", "trafo", "karanlık", "lamba", "electric", "power")):
            category = "electrical"
        elif any(w in lower for w in ("asfalt", "çukur", "yol", "kaldırım", "pavement", "road", "pothole")):
            category = "pavement"
        elif any(w in lower for w in ("yangın", "gaz", "patlama", "zehir", "çökme", "hazard", "gas", "fire")):
            category = "hazmat"
        elif any(w in lower for w in ("internet", "fiber", "şebeke", "network")):
            category = "networking"
        else:
            category = "general"

        # Urgency scoring
        critical_words = ("acil", "yangın", "patlama", "tehlike", "zehir", "çökme", "danger", "urgent", "critical")
        high_words = ("hasar", "patlak", "çukur", "kaza", "döküldü", "koptu", "leak", "outage")
        if any(w in lower for w in critical_words):
            urgency = 0.95
        elif any(w in lower for w in high_words):
            urgency = 0.75
        elif category in ("hazmat", "electrical"):
            urgency = 0.65
        else:
            urgency = 0.35

        return urgency, category

    async def process_report(self, request: TriageReportRequest) -> TriageOutcome:
        """Executes full multimodal validation, PII redaction, deduplication, and persistence."""
        # 1. Text completeness validation
        words = request.description.strip().split()
        if len(words) < MIN_TEXT_WORDS:
            return TriageOutcome(
                status="clarification_required",
                message=f"Description is too brief ({len(words)} words). Please provide more context about the incident.",
            )

        # 2. Image validation (if attached)
        if request.image_url and (request.image_url.startswith("data:image") or len(request.image_url) > 100):
            valid_img, img_msg, _ = self.validate_image_data(request.image_url)
            if not valid_img:
                return TriageOutcome(
                    status="clarification_required",
                    message=img_msg,
                )

        # 3. PII redaction
        clean_text, redactions = self.redactor.redact(request.description)

        # 4. Generate dense embedding
        embedding = await self.dedup_service.compute_embedding(clean_text)

        # 5. Urgency & Category estimation
        urgency, category = self.estimate_urgency_and_category(clean_text)
        if request.category:
            category = request.category

        # 6. Database transaction with advisory lock & deduplication
        lock_key = f"triage_lock_{category}_{hashlib.md5(clean_text[:50].encode()).hexdigest()[:8]}"

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Acquire advisory lock to prevent race conditions during deduplication
                await self.dedup_service.acquire_advisory_lock(conn, lock_key)

                # Check for existing duplicate ticket
                duplicate_id, similarity = await self.dedup_service.find_duplicate(conn, embedding, category)
                if duplicate_id and similarity is not None:
                    await self.dedup_service.merge_into_ticket(conn, duplicate_id, similarity, request.user_id)
                    return TriageOutcome(
                        status="merged_duplicate",
                        message=f"Report matched existing ticket {duplicate_id} with similarity {similarity:.3f}. Merged.",
                        ticket_id=duplicate_id,
                        similarity=similarity,
                        cleaned_description=clean_text,
                        urgency_score=urgency,
                        category=category,
                    )

                # Insert new unique ticket
                ticket_id = uuid4()
                insert_ticket_sql = """
                    INSERT INTO tickets (
                        id, user_id, raw_description, cleaned_description,
                        image_url, category, urgency_score, status, report_count
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', 1);
                """
                await conn.execute(
                    insert_ticket_sql,
                    ticket_id,
                    request.user_id,
                    request.description,
                    clean_text,
                    request.image_url,
                    category,
                    urgency,
                )

                # Insert vector embedding into ticket_embeddings
                insert_emb_sql = """
                    INSERT INTO ticket_embeddings (ticket_id, embedding, metadata)
                    VALUES ($1, $2, $3::jsonb);
                """
                metadata = {
                    "category": category,
                    "urgency": urgency,
                    "redactions": redactions,
                }
                import json
                await conn.execute(insert_emb_sql, ticket_id, embedding, json.dumps(metadata))

        # 7. Asynchronously notify RabbitMQ
        await self._publish_to_rabbitmq(ticket_id, clean_text, category, urgency)

        return TriageOutcome(
            status="created",
            message=f"Ticket {ticket_id} created successfully.",
            ticket_id=ticket_id,
            similarity=0.0,
            cleaned_description=clean_text,
            urgency_score=urgency,
            category=category,
        )

    async def _publish_to_rabbitmq(
        self, ticket_id: UUID, text: str, category: str, urgency: float
    ) -> None:
        """Publishes ticket event to RabbitMQ triage exchange."""
        if not self.rabbitmq_channel:
            return
        try:
            import json
            import aio_pika
            payload = json.dumps(
                {
                    "event": "ticket_created",
                    "ticket_id": str(ticket_id),
                    "category": category,
                    "urgency": urgency,
                    "preview": text[:100],
                }
            ).encode("utf-8")

            await self.rabbitmq_channel.default_exchange.publish(
                aio_pika.Message(body=payload, content_type="application/json"),
                routing_key="triage_queue",
            )
            logger.info("Published ticket %s to RabbitMQ", ticket_id)
        except Exception as exc:
            logger.warning("RabbitMQ event publish failed: %s", exc)
