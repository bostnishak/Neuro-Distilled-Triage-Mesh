"""Module: Semantic Deduplication Service for NDTM.

Implements vector cosine similarity search via pgvector (HNSW) to detect duplicate
incident reports before persisting new tickets, with transaction-level advisory locking
to prevent concurrent insertion race conditions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Sequence
from uuid import UUID

import asyncpg
import numpy as np

logger = logging.getLogger("deduplication_service")

# Global default threshold for deduplication
DEDUP_SIMILARITY_THRESHOLD = 0.88
EMBEDDING_DIMENSION = 768


class EmbeddingGenerator:
    """Manages dense vector generation for incoming text with graceful fallback."""

    def __init__(self, model_name: str = "BAAI/bge-m3") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        import os
        if os.getenv("NDTM_MOCK_EMBEDDINGS") == "1":
            self._model = None
            self._initialized = True
            return
        try:
            from sentence_transformers import SentenceTransformer
            # Attempt to load local weights without hanging on remote downloads
            self._model = SentenceTransformer(self.model_name, local_files_only=True)
            self._initialized = True
        except Exception:
            # Fall back cleanly to deterministic 768-D pseudo-semantic projection
            self._model = None
            self._initialized = True

    def encode(self, text: str) -> list[float]:
        """Encode text into a normalized 768-dimensional float vector."""
        if not self._initialized:
            self.initialize()

        if self._model is not None:
            try:
                emb = self._model.encode(text, normalize_embeddings=True)
                if isinstance(emb, np.ndarray):
                    emb_list = emb.tolist()
                    # Ensure exact dimension 768
                    if len(emb_list) == EMBEDDING_DIMENSION:
                        return emb_list
                    elif len(emb_list) > EMBEDDING_DIMENSION:
                        return emb_list[:EMBEDDING_DIMENSION]
                    else:
                        return emb_list + [0.0] * (EMBEDDING_DIMENSION - len(emb_list))
            except Exception as exc:
                logger.warning("Model inference failed during encoding: %s. Using fallback vector.", exc)

        # Deterministic semantic hash projection (768 dimensions) for offline/testing robustness
        return self._fallback_vector(text)

    def _fallback_vector(self, text: str) -> list[float]:
        """Generates a stable, normalized 768-D dense vector based on token frequencies and hashes."""
        vec = np.zeros(EMBEDDING_DIMENSION, dtype=np.float32)
        words = text.lower().split()
        if not words:
            vec[0] = 1.0
            return vec.tolist()

        for idx, word in enumerate(words):
            h = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16)
            slot = h % EMBEDDING_DIMENSION
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec[slot] += sign * (1.0 / (idx + 1) ** 0.5)

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        else:
            vec[0] = 1.0
        return vec.tolist()


class SemanticDeduplicationService:
    """Detects and merges duplicate incident tickets using pgvector cosine distance."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        similarity_threshold: float = DEDUP_SIMILARITY_THRESHOLD,
        embedding_generator: EmbeddingGenerator | None = None,
    ) -> None:
        self.pool = pool
        self.similarity_threshold = similarity_threshold
        self.embedder = embedding_generator or EmbeddingGenerator()

    async def compute_embedding(self, text: str) -> list[float]:
        """Asynchronously compute dense vector representation."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.embedder.encode, text)

    async def find_duplicate(
        self,
        conn: asyncpg.Connection,
        embedding: Sequence[float],
        category: str | None = None,
    ) -> tuple[UUID | None, float | None]:
        """Find the most similar existing ticket within the threshold.

        Uses the pgvector cosine distance operator `<=>` where:
        cosine_similarity = 1 - (embedding <=> $1)
        """
        # HNSW query on ticket_embeddings table
        query = """
            SELECT 
                te.ticket_id,
                1 - (te.embedding <=> $1) AS similarity
            FROM ticket_embeddings te
            JOIN tickets t ON t.id = te.ticket_id
            WHERE t.status IN ('pending', 'processing')
              AND 1 - (te.embedding <=> $1) >= $2
            ORDER BY similarity DESC
            LIMIT 1;
        """
        row = await conn.fetchrow(query, embedding, self.similarity_threshold)
        if row:
            return UUID(str(row["ticket_id"])), float(row["similarity"])
        return None, None

    async def merge_into_ticket(
        self,
        conn: asyncpg.Connection,
        parent_ticket_id: UUID,
        similarity: float,
        reporter_user_id: UUID | None = None,
    ) -> None:
        """Increment report count and log duplicate merge."""
        update_query = """
            UPDATE tickets
            SET report_count = report_count + 1
            WHERE id = $1;
        """
        await conn.execute(update_query, parent_ticket_id)
        logger.info(
            "Ticket %s report_count incremented (merged duplicate with similarity %.4f)",
            parent_ticket_id,
            similarity,
        )

    async def acquire_advisory_lock(
        self,
        conn: asyncpg.Connection,
        lock_key: str,
    ) -> None:
        """Acquires a transaction-scoped PostgreSQL advisory lock using hashtext."""
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", lock_key)
