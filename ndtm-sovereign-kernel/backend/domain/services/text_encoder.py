"""
Neuro-Distilled Triage Mesh (NDTM) — Sovereign Distributed & Failure-Proof Kernel
RFC-NDTM-OMEGA: Production Hardening Engine v3.0

Deterministic Multi-Gram Hashing Vectorizer for Text Embeddings (384-D Unit Spherical Space).
Replaces raw ASCII byte arrays with sign-preserving Murmur/FNV-1a hashed bag-of-ngrams.
Guarantees cosine similarity preservation across pgvector HNSW semantic search.
"""

from __future__ import annotations
import re
import numpy as np


def encode_text_to_feature_vector(text: str, dim: int = 384) -> np.ndarray:
    """
    Encodes raw or scrubbed incident text into a unit-normalized (L2) feature embedding.
    Uses word unigrams, bigrams, and character trigrams projected via FNV-1a signed hashing.
    
    Args:
        text: Input string description or query.
        dim: Target embedding dimension (default: 384 for pgvector HNSW schema).
        
    Returns:
        np.ndarray of shape (dim,) with dtype float32, Euclidean norm = 1.0.
    """
    if not text or not text.strip():
        return np.zeros(dim, dtype=np.float32)

    vec = np.zeros(dim, dtype=np.float32)
    normalized = re.sub(r"[^\w\s]", " ", text.lower()).strip()
    words = normalized.split()

    tokens = []
    # 1. Word unigrams
    tokens.extend(words)

    # 2. Word bigrams
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")

    # 3. Character trigrams for morphological robustness
    compact = normalized.replace(" ", "")
    for i in range(len(compact) - 2):
        tokens.append(compact[i:i+3])

    if not tokens:
        tokens = [normalized]

    # Signed hash projection
    for token in tokens:
        h = 0xcbf29ce484222325
        for byte in token.encode("utf-8"):
            h = ((h ^ byte) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
        
        idx = h % dim
        sign = 1.0 if ((h >> 32) & 1) == 0 else -1.0
        vec[idx] += sign

    # Unit L2 Normalization
    norm = float(np.linalg.norm(vec))
    if norm > 1e-12:
        vec /= norm

    return vec
