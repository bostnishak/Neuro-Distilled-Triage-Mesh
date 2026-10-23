"""Module 1 — Active Multimodal Triage & Semantic Deduplication Gateway.

Pipeline for every incoming citizen report (text + image):

1. **Active validation** (before any DB commit)
   * Deterministic image-quality gate: decodability, format, resolution,
     sharpness (variance of Laplacian) and exposure.
   * Text completeness: length / word count and location context.
   * Optional Vision-Language Model check: is the photo relevant to the
     description and is anything essential missing?
   Any failure returns *clarification questions* instead of persisting junk.

2. **Semantic deduplication**
   * Embed the description (multilingual-e5 / bge-m3).
   * Query pgvector (HNSW, cosine) for active tickets in the same
     geographic bounding box / category cluster.
   * similarity >= DEDUP_SIMILARITY_THRESHOLD (0.88) => merge into the master
     ticket and notify the reporter.
   * A transaction-scoped advisory lock per geo-cell serialises concurrent
     submissions so two simultaneous duplicates cannot both create tickets.

3. **Asynchronous routing**
   * Unique reports create a ticket + embedding + outbox event atomically;
     the outbox relay publishes to RabbitMQ `triage_queue`.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from core.audit import write_audit
from core.config import Settings
from core.embeddings import EmbeddingService
from core.llm import LLMClient, LLMError
from core.logging_config import request_id_ctx
from core.outbox import OutboxRelay, enqueue_outbox

logger = logging.getLogger(__name__)

# Guard against decompression bombs (default Pillow limit is ~89MP).
Image.MAX_IMAGE_PIXELS = 40_000_000

_ALLOWED_FORMATS: dict[str, str] = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_ACTIVE_STATUSES = ("pending_triage", "triaged", "in_progress")
_KM_PER_DEG_LAT = 111.32


# =============================================================================
# Public models
# =============================================================================
class SubmissionStatus(str, Enum):
    QUEUED = "queued"
    MERGED = "merged_duplicate"
    CLARIFICATION_REQUIRED = "clarification_required"


class ClarificationQuestion(BaseModel):
    code: str = Field(description="Machine-readable reason, e.g. IMAGE_BLURRY")
    field: str = Field(description="Form field the user should fix: image | description | location")
    question: str = Field(description="Human-readable prompt shown to the reporter")


class ImageQualityReport(BaseModel):
    valid: bool
    format: str | None = None
    width: int | None = None
    height: int | None = None
    blur_score: float | None = Field(None, description="Variance of Laplacian (higher = sharper)")
    brightness: float | None = Field(None, description="Mean luminance 0-255")
    sha256: str | None = None
    issues: list[str] = Field(default_factory=list)


class TriageOutcome(BaseModel):
    status: SubmissionStatus
    message: str
    ticket_id: UUID | None = None
    report_id: UUID | None = None
    similarity: float | None = None
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    image_quality: ImageQualityReport | None = None


@dataclass(slots=True)
class ReportSubmission:
    """Normalised input from the HTTP layer."""

    description: str
    image_bytes: bytes | None = None
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    category: str | None = None
    reporter_email: str | None = None
    reporter_name: str | None = None


@dataclass(slots=True)
class DuplicateMatch:
    ticket_id: UUID
    similarity: float


# =============================================================================
# Image quality gate (deterministic, CPU-cheap)
# =============================================================================
class ImageQualityInspector:
    """Heuristic image gate. Runs in a worker thread (`asyncio.to_thread`)."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def inspect(self, data: bytes) -> ImageQualityReport:
        sha = hashlib.sha256(data).hexdigest()
        try:
            with Image.open(io.BytesIO(data)) as probe:
                fmt = probe.format
                probe.verify()  # detects truncated / corrupt files
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
            logger.info("Unreadable image rejected: %s", exc)
            return ImageQualityReport(valid=False, sha256=sha, issues=["IMAGE_UNREADABLE"])

        if fmt not in _ALLOWED_FORMATS:
            return ImageQualityReport(valid=False, format=fmt, sha256=sha, issues=["IMAGE_UNSUPPORTED_FORMAT"])

        with Image.open(io.BytesIO(data)) as raw:
            img = ImageOps.exif_transpose(raw)
            width, height = img.size
            gray = img.convert("L")
            gray.thumbnail((512, 512))  # normalise scale so the blur threshold is resolution-independent
            arr = np.asarray(gray, dtype=np.float32)

        brightness = float(arr.mean())
        # Discrete Laplacian via array shifts (no OpenCV dependency).
        lap = arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:] - 4.0 * arr[1:-1, 1:-1]
        blur_score = float(lap.var()) if lap.size else 0.0

        issues: list[str] = []
        if width < self._s.min_image_width or height < self._s.min_image_height:
            issues.append("IMAGE_LOW_RESOLUTION")
        if blur_score < self._s.blur_threshold:
            issues.append("IMAGE_BLURRY")
        if brightness < self._s.min_brightness:
            issues.append("IMAGE_TOO_DARK")
        elif brightness > self._s.max_brightness:
            issues.append("IMAGE_OVEREXPOSED")

        return ImageQualityReport(
            valid=not issues, format=fmt, width=width, height=height,
            blur_score=round(blur_score, 2), brightness=round(brightness, 2), sha256=sha, issues=issues,
        )


_IMAGE_QUESTIONS: dict[str, str] = {
    "IMAGE_MISSING": "Please attach a photo of the issue so our crews can assess it.",
    "IMAGE_UNREADABLE": "We couldn't open your photo. Please upload a JPEG, PNG or WEBP image.",
    "IMAGE_UNSUPPORTED_FORMAT": "That image format isn't supported. Please upload a JPEG, PNG or WEBP photo.",
    "IMAGE_LOW_RESOLUTION": "The photo resolution is too low. Please upload a larger, closer photo.",
    "IMAGE_BLURRY": "Your photo looks blurry. Could you retake it while holding the camera steady?",
    "IMAGE_TOO_DARK": "The photo is too dark to see the problem. Please retake it with more light or flash.",
    "IMAGE_OVEREXPOSED": "The photo is overexposed. Please retake it avoiding direct glare.",
}


# =============================================================================
# Optional Vision-Language Model inspector
# =============================================================================
class VisionLanguageInspector:
    """Asks a VLM whether the image supports the description and what's missing."""

    _SYSTEM = (
        "You are the quality gate of a public-infrastructure and IT issue reporting system. "
        "Given a citizen's photo and description, decide whether the report is actionable by a field crew. "
        "Respond ONLY with JSON: {\"image_relevant\": bool, \"image_clear\": bool, "
        "\"description_complete\": bool, \"missing_information\": [string], "
        "\"follow_up_question\": string|null}. Ask at most ONE short, polite follow-up question."
    )

    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._s = settings

    @property
    def enabled(self) -> bool:
        return self._s.vlm_enabled and self._llm.available

    @staticmethod
    def _to_jpeg_b64(data: bytes, max_side: int = 768) -> str:
        with Image.open(io.BytesIO(data)) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    async def inspect(self, description: str, image_bytes: bytes) -> list[ClarificationQuestion]:
        if not self.enabled:
            return []
        b64 = await asyncio.to_thread(self._to_jpeg_b64, image_bytes)
        messages = [
            {"role": "system", "content": self._SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": f"Citizen description:\n{description}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]},
        ]
        try:
            data = await self._llm.chat_json(messages, model=self._s.vlm_model, max_tokens=400)
        except LLMError as exc:
            logger.warning("VLM inspection failed (fail_open=%s): %s", self._s.vlm_fail_open, exc)
            if self._s.vlm_fail_open:
                return []
            return [ClarificationQuestion(code="VLM_UNAVAILABLE", field="image",
                                          question="We couldn't verify your photo right now. Please retry shortly.")]

        questions: list[ClarificationQuestion] = []
        if data.get("image_relevant") is False:
            questions.append(ClarificationQuestion(
                code="IMAGE_IRRELEVANT", field="image",
                question="The photo doesn't seem to show the issue you described. Please attach a photo of it."))
        if data.get("image_clear") is False:
            questions.append(ClarificationQuestion(
                code="IMAGE_UNCLEAR", field="image",
                question="The problem isn't clearly visible in the photo. Could you take a closer shot?"))
        if data.get("description_complete") is False:
            follow_up = data.get("follow_up_question") or "Could you add a bit more detail about the problem?"
            questions.append(ClarificationQuestion(code="DESCRIPTION_INCOMPLETE", field="description",
                                                   question=str(follow_up)[:500]))
        return questions


# =============================================================================
# Triage service
# =============================================================================
class TriageService:
    """Orchestrates validation, deduplication, persistence and async routing."""

    def __init__(self, pool: asyncpg.Pool, embedder: EmbeddingService, llm: LLMClient,
                 relay: OutboxRelay, settings: Settings) -> None:
        self._pool = pool
        self._embedder = embedder
        self._relay = relay
        self._s = settings
        self._image_inspector = ImageQualityInspector(settings)
        self._vlm = VisionLanguageInspector(llm, settings)
        self._upload_dir = Path(settings.upload_dir)

    # ------------------------------------------------------------------ public
    async def submit(self, sub: ReportSubmission) -> TriageOutcome:
        """Validate → sanitize & redact PII → deduplicate → persist/merge → enqueue."""
        from middleware.telemetry_and_security import redact_pii, sanitize_input_text

        # Security & Privacy: Sanitize prompt injection triggers and redact PII before DB & Embeddings
        sub.description = sanitize_input_text(redact_pii(sub.description))
        if sub.address:
            sub.address = sanitize_input_text(redact_pii(sub.address))

        questions, quality = await self._validate(sub)
        if questions:
            logger.info("Report needs clarification", extra={"codes": [q.code for q in questions]})
            return TriageOutcome(
                status=SubmissionStatus.CLARIFICATION_REQUIRED,
                message="We need a little more information before we can file your report.",
                questions=questions,
                image_quality=quality,
            )

        image_path = await self._store_image(sub.image_bytes, quality) if sub.image_bytes and quality else None
        embedding = await self._embedder.embed(sub.description)


        async with self._pool.acquire() as conn, conn.transaction():
            # Serialise dedup decisions per coarse geo-cell (~11km) to avoid duplicate-ticket races.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", self._lock_key(sub))
            user_id = await self._upsert_user(conn, sub)
            match = await self._find_duplicate(conn, embedding, sub)

            if match and match.similarity >= self._s.dedup_similarity_threshold:
                outcome = await self._merge(conn, sub, match, user_id, image_path, quality)
            else:
                outcome = await self._create(conn, sub, embedding, user_id, image_path, quality,
                                             nearest=match)

        if outcome.status is SubmissionStatus.QUEUED:
            self._relay.notify()  # publish the outbox event right away
        return outcome

    # ------------------------------------------------------------------ validation
    async def _validate(self, sub: ReportSubmission) -> tuple[list[ClarificationQuestion],
                                                               ImageQualityReport | None]:
        questions: list[ClarificationQuestion] = []
        quality: ImageQualityReport | None = None

        # --- text completeness
        text = sub.description.strip()
        if len(text) < self._s.min_description_chars or len(text.split()) < self._s.min_description_words:
            questions.append(ClarificationQuestion(
                code="DESCRIPTION_TOO_SHORT", field="description",
                question="Please describe the problem in a sentence or two (what, how severe, since when)."))

        # --- location context
        has_coords = sub.latitude is not None and sub.longitude is not None
        if (sub.latitude is None) != (sub.longitude is None):
            questions.append(ClarificationQuestion(
                code="LOCATION_INCOMPLETE", field="location",
                question="Both latitude and longitude are required when sharing GPS coordinates."))
        elif not has_coords and not (sub.address and len(sub.address.strip()) >= 5):
            questions.append(ClarificationQuestion(
                code="LOCATION_MISSING", field="location",
                question="Where is this? Please share your GPS location or a street address / nearby landmark."))

        # --- image quality
        if sub.image_bytes:
            quality = await asyncio.to_thread(self._image_inspector.inspect, sub.image_bytes)
            for code in quality.issues:
                questions.append(ClarificationQuestion(code=code, field="image",
                                                       question=_IMAGE_QUESTIONS.get(code, "Please retake the photo.")))
        elif self._s.require_image:
            questions.append(ClarificationQuestion(code="IMAGE_MISSING", field="image",
                                                   question=_IMAGE_QUESTIONS["IMAGE_MISSING"]))

        # --- semantic check with VLM (only when the cheap checks passed, to save cost)
        if not questions and sub.image_bytes and quality and quality.valid:
            questions.extend(await self._vlm.inspect(text, sub.image_bytes))

        return questions, quality

    # ------------------------------------------------------------------ dedup
    def _lock_key(self, sub: ReportSubmission) -> str:
        if sub.latitude is None or sub.longitude is None:
            return "dedup:no-geo"
        return f"dedup:{sub.latitude:.1f}:{sub.longitude:.1f}"

    async def _find_duplicate(self, conn: asyncpg.Connection, embedding: np.ndarray,
                              sub: ReportSubmission) -> DuplicateMatch | None:
        """Nearest active ticket (cosine) inside the geo/category cluster."""
        params: list[Any] = [embedding, list(_ACTIVE_STATUSES)]
        conditions = ["t.status::text = ANY($2::text[])"]

        if sub.latitude is not None and sub.longitude is not None:
            d_lat = self._s.dedup_radius_km / _KM_PER_DEG_LAT
            d_lon = self._s.dedup_radius_km / (_KM_PER_DEG_LAT * max(math.cos(math.radians(sub.latitude)), 0.01))
            params.extend([sub.latitude - d_lat, sub.latitude + d_lat, sub.longitude - d_lon, sub.longitude + d_lon])
            n = len(params)
            conditions.append(f"t.latitude BETWEEN ${n - 3} AND ${n - 2} AND t.longitude BETWEEN ${n - 1} AND ${n}")

        if sub.category:
            params.append(sub.category)
            # Tickets not yet triaged (NULL category) are still candidates.
            conditions.append(f"(t.category IS NULL OR t.category = ${len(params)})")

        sql = f"""
            SELECT t.id, 1 - (e.embedding <=> $1::vector) AS similarity
            FROM ticket_embeddings e
            JOIN tickets t ON t.id = e.ticket_id
            WHERE {' AND '.join(conditions)}
            ORDER BY e.embedding <=> $1::vector
            LIMIT 1
        """
        row = await conn.fetchrow(sql, *params)
        if row is None:
            return None
        return DuplicateMatch(ticket_id=row["id"], similarity=float(row["similarity"]))

    # ------------------------------------------------------------------ persistence
    async def _upsert_user(self, conn: asyncpg.Connection, sub: ReportSubmission) -> UUID | None:
        if not sub.reporter_email:
            return None
        return await conn.fetchval(
            """
            INSERT INTO users (email, display_name) VALUES ($1, $2)
            ON CONFLICT (email) DO UPDATE
                SET display_name = COALESCE(EXCLUDED.display_name, users.display_name)
            RETURNING id
            """,
            sub.reporter_email.strip().lower(), sub.reporter_name,
        )

    async def _insert_report(self, conn: asyncpg.Connection, *, ticket_id: UUID, sub: ReportSubmission,
                             user_id: UUID | None, image_path: str | None,
                             quality: ImageQualityReport | None, outcome: str,
                             similarity: float | None) -> UUID:
        return await conn.fetchval(
            """
            INSERT INTO reports (ticket_id, user_id, description, image_path, image_sha256, image_quality,
                                 latitude, longitude, address, outcome, similarity, request_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::report_outcome, $11, $12)
            RETURNING id
            """,
            ticket_id, user_id, sub.description, image_path,
            quality.sha256 if quality else None,
            quality.model_dump(mode="json") if quality else None,
            sub.latitude, sub.longitude, sub.address, outcome, similarity, request_id_ctx.get(),
        )

    async def _merge(self, conn: asyncpg.Connection, sub: ReportSubmission, match: DuplicateMatch,
                     user_id: UUID | None, image_path: str | None,
                     quality: ImageQualityReport | None) -> TriageOutcome:
        report_id = await self._insert_report(conn, ticket_id=match.ticket_id, sub=sub, user_id=user_id,
                                              image_path=image_path, quality=quality,
                                              outcome="merged_duplicate", similarity=match.similarity)
        report_count = await conn.fetchval(
            """
            UPDATE tickets SET report_count = report_count + 1, last_reported_at = now()
            WHERE id = $1 RETURNING report_count
            """,
            match.ticket_id,
        )
        message = (
            f"Thanks! This issue is already being tracked as ticket {match.ticket_id} "
            f"({report_count} reports, {match.similarity:.0%} match). We merged your report so crews "
            f"see the added impact, and we'll notify you on progress."
        )
        await conn.execute("INSERT INTO notifications (user_id, ticket_id, message) VALUES ($1, $2, $3)",
                           user_id, match.ticket_id, message)
        await write_audit(conn, entity_type="ticket", entity_id=match.ticket_id, action="report_merged",
                          details={"report_id": str(report_id), "similarity": round(match.similarity, 4),
                                   "report_count": report_count})
        logger.info("Duplicate merged", extra={"ticket_id": str(match.ticket_id),
                                               "similarity": round(match.similarity, 4)})
        return TriageOutcome(status=SubmissionStatus.MERGED, message=message, ticket_id=match.ticket_id,
                             report_id=report_id, similarity=round(match.similarity, 4), image_quality=quality)

    async def _create(self, conn: asyncpg.Connection, sub: ReportSubmission, embedding: np.ndarray,
                      user_id: UUID | None, image_path: str | None, quality: ImageQualityReport | None,
                      nearest: DuplicateMatch | None) -> TriageOutcome:
        title = sub.description.strip().splitlines()[0][:120]
        ticket_id: UUID = await conn.fetchval(
            """
            INSERT INTO tickets (title, description, category, latitude, longitude, address, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
            """,
            title, sub.description, sub.category, sub.latitude, sub.longitude, sub.address, user_id,
        )
        await conn.execute(
            "INSERT INTO ticket_embeddings (ticket_id, model_name, embedding) VALUES ($1, $2, $3)",
            ticket_id, self._embedder.model_name, embedding,
        )
        report_id = await self._insert_report(conn, ticket_id=ticket_id, sub=sub, user_id=user_id,
                                              image_path=image_path, quality=quality,
                                              outcome="created_ticket", similarity=None)
        await enqueue_outbox(conn, aggregate_id=ticket_id, routing_key=self._s.triage_routing_key, payload={
            "event": "ticket.created",
            "ticket_id": str(ticket_id),
            "report_id": str(report_id),
            "request_id": request_id_ctx.get(),
        })
        message = f"Your report was received as ticket {ticket_id} and is being triaged."
        await conn.execute("INSERT INTO notifications (user_id, ticket_id, message) VALUES ($1, $2, $3)",
                           user_id, ticket_id, message)
        await write_audit(conn, entity_type="ticket", entity_id=ticket_id, action="ticket_created", details={
            "report_id": str(report_id),
            "nearest_ticket": str(nearest.ticket_id) if nearest else None,
            "nearest_similarity": round(nearest.similarity, 4) if nearest else None,
        })
        logger.info("Ticket created", extra={"ticket_id": str(ticket_id)})
        return TriageOutcome(status=SubmissionStatus.QUEUED, message=message, ticket_id=ticket_id,
                             report_id=report_id, image_quality=quality,
                             similarity=round(nearest.similarity, 4) if nearest else None)

    async def _store_image(self, data: bytes, quality: ImageQualityReport) -> str:
        """Content-addressed storage (idempotent; re-uploads of the same photo reuse the file)."""
        assert quality.sha256 and quality.format
        ext = _ALLOWED_FORMATS[quality.format]
        path = self._upload_dir / quality.sha256[:2] / f"{quality.sha256}.{ext}"

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)  # atomic rename

        await asyncio.to_thread(_write)
        return str(path)
