"""Unit and Mock Integration tests for Deduplication Engine and Vector Embeddings."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock
from uuid import uuid4

import numpy as np
import pytest

from backend.services.deduplication_engine import (
    DeduplicationEngine,
    TextEmbeddingService,
)


class TestTextEmbeddingService:
    """Verifies dense vector encoding properties."""

    def setup_method(self):
        self.service = TextEmbeddingService()

    def test_embedding_dimension(self):
        emb = self.service.encode("Elektrik trafosu patladı, yangın var.")
        assert len(emb) == 384
        assert all(isinstance(x, float) for x in emb)

    def test_unit_normalization(self):
        emb = self.service.encode("Ana su borusu patladı ve cadde sular altında.")
        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-4

    def test_deterministic_cosine_similarity(self):
        text_a = "Sokakta derin bir çukur var"
        text_b = "Sokakta derin bir çukur var"
        text_c = "Gökyüzünde parlak bir kuyruklu yıldız görüldü"

        emb_a = np.array(self.service.encode(text_a))
        emb_b = np.array(self.service.encode(text_b))
        emb_c = np.array(self.service.encode(text_c))

        sim_identical = float(np.dot(emb_a, emb_b))
        sim_different = float(np.dot(emb_a, emb_c))

        assert abs(sim_identical - 1.0) < 1e-4
        assert sim_different < 0.85


class TestDeduplicationEngine:
    """Verifies Deduplication Engine logic and SQL query handling."""

    @pytest.mark.asyncio
    async def test_duplicate_found(self):
        engine = DeduplicationEngine(similarity_threshold=0.86, radius_meters=250.0)
        parent_id = uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {
            "id": parent_id,
            "category": "INFRASTRUCTURE_HAZARD",
            "duplicate_count": 3,
            "cosine_sim": 0.942,
            "distance_meters": 45.2,
        }

        dummy_emb = [0.0] * 384
        dummy_emb[0] = 1.0

        match = await engine.query_duplicate(
            conn=mock_conn,
            embedding=dummy_emb,
            longitude=28.9784,
            latitude=41.0082,
        )

        assert match.is_duplicate is True
        assert match.parent_id == parent_id
        assert match.duplicate_count == 3
        assert match.cosine_similarity == 0.942
        assert match.distance_meters == 45.2
        assert match.category == "INFRASTRUCTURE_HAZARD"

    @pytest.mark.asyncio
    async def test_no_duplicate_found(self):
        engine = DeduplicationEngine()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        dummy_emb = [0.0] * 384
        dummy_emb[0] = 1.0

        match = await engine.query_duplicate(
            conn=mock_conn,
            embedding=dummy_emb,
            longitude=28.9784,
            latitude=41.0082,
        )

        assert match.is_duplicate is False
        assert match.parent_id is None
        assert match.duplicate_count == 1
        assert match.cosine_similarity == 0.0
