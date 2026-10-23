"""Sentence-embedding service (multilingual-e5 / bge-m3 via sentence-transformers)."""
from __future__ import annotations

import asyncio
import logging
import time

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Loads a SentenceTransformer once and serves L2-normalised float32 embeddings.

    Encoding runs in a worker thread (torch releases the GIL) and concurrency is
    bounded by a semaphore to protect CPU / memory under load.
    """

    def __init__(self, model_name: str, expected_dim: int, device: str = "cpu", prefix: str = "",
                 max_concurrency: int = 4) -> None:
        self.model_name = model_name
        self.expected_dim = expected_dim
        self.device = device
        self.prefix = prefix
        self._model = None
        self._sem = asyncio.Semaphore(max_concurrency)

    @property
    def ready(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Blocking model load. Call via `asyncio.to_thread` from async code."""
        from sentence_transformers import SentenceTransformer  # heavy import, keep lazy

        started = time.perf_counter()
        model = SentenceTransformer(self.model_name, device=self.device)
        dim = model.get_sentence_embedding_dimension()
        if dim != self.expected_dim:
            raise RuntimeError(
                f"Embedding model {self.model_name} produces {dim}-d vectors but EMBEDDING_DIM="
                f"{self.expected_dim}. Update EMBEDDING_DIM and vector(N) in database/schema.sql."
            )
        self._model = model
        logger.info("Embedding model loaded", extra={"model": self.model_name, "dim": dim,
                                                     "load_s": round(time.perf_counter() - started, 2)})

    def encode_sync(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("Embedding model not loaded")
        vectors = self._model.encode(
            [f"{self.prefix}{t}" for t in texts],
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    async def embed(self, text: str) -> np.ndarray:
        async with self._sem:
            return (await asyncio.to_thread(self.encode_sync, [text]))[0]
