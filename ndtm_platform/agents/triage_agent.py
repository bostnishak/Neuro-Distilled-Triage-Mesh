"""Module: Triage & Domain Specialist Agent.

Categorizes the ticket, generates embeddings, retrieves historical context and similar
past tickets via pgvector, and assesses initial domain severity.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from ndtm_platform.services.deduplication_service import EmbeddingGenerator

logger = logging.getLogger("triage_agent")


class TriageSpecialistAgent:
    """Specialized agent responsible for domain categorization and historical vector retrieval."""

    def __init__(self, pool: asyncpg.Pool, embedder: EmbeddingGenerator | None = None) -> None:
        self.pool = pool
        self.embedder = embedder or EmbeddingGenerator()

    async def analyze(
        self,
        description: str,
        category_hint: str | None = None,
        ticket_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Analyzes ticket, extracts intent, and retrieves similar historical cases."""
        # 1. Compute embedding
        emb = self.embedder.encode(description)

        # 2. Query historical tickets via pgvector
        historical_matches: list[dict[str, Any]] = []
        try:
            async with self.pool.acquire() as conn:
                query = """
                    SELECT 
                        t.id,
                        t.category,
                        t.urgency_score,
                        t.status,
                        t.cleaned_description,
                        1 - (te.embedding <=> $1) AS similarity
                    FROM ticket_embeddings te
                    JOIN tickets t ON t.id = te.ticket_id
                    WHERE t.status IN ('resolved', 'processing')
                    ORDER BY similarity DESC
                    LIMIT 3;
                """
                rows = await conn.fetch(query, emb)
                for r in rows:
                    historical_matches.append({
                        "ticket_id": str(r["id"]),
                        "category": r["category"],
                        "urgency": float(r["urgency_score"] or 0.5),
                        "status": str(r["status"]),
                        "similarity": round(float(r["similarity"]), 3),
                        "snippet": r["cleaned_description"][:80],
                    })
        except Exception as exc:
            logger.warning("Historical vector retrieval error: %s", exc)

        # 3. Categorization logic
        lower = description.lower()
        if any(w in lower for w in ("kimyasal", "gaz", "patlama", "zehir", "yangın", "hazard", "fire")):
            category = "hazmat"
            confidence = 0.96
            urgency = 0.95
        elif any(w in lower for w in ("elektrik", "trafo", "kablo", "lamba", "electric", "power")):
            category = "electrical"
            confidence = 0.92
            urgency = 0.80
        elif any(w in lower for w in ("su", "boru", "patlak", "kanal", "leak", "water")):
            category = "plumbing"
            confidence = 0.94
            urgency = 0.75
        elif any(w in lower for w in ("yol", "asfalt", "çukur", "kaldırım", "pothole")):
            category = "pavement"
            confidence = 0.90
            urgency = 0.60
        else:
            category = category_hint or "general"
            # If ambiguous or lacking keywords, confidence drops (can trigger HITL if needed!)
            confidence = 0.82 if len(description.split()) < 8 else 0.88
            urgency = 0.40

        # Adjust confidence based on historical matches
        if historical_matches and historical_matches[0]["similarity"] > 0.85:
            confidence = min(1.0, confidence + 0.05)

        return {
            "agent": "TriageSpecialistAgent",
            "category": category,
            "confidence": round(confidence, 3),
            "urgency": round(urgency, 2),
            "historical_context": historical_matches,
            "historical_match_count": len(historical_matches),
            "reasoning": f"Identified category '{category}' with urgency {urgency:.2f} based on domain keywords and {len(historical_matches)} historical vector matches.",
        }
