"""Prefix KV-Cache Management for High-Throughput Token Sharing."""
from __future__ import annotations

import hashlib
from typing import Any


class PrefixKVCache:
    """Stores precomputed key-value activation states for common prompt prefixes."""

    def __init__(self, max_entries: int = 1000) -> None:
        self.max_entries = max_entries
        self._cache: dict[str, dict[str, Any]] = {}
        self._hits = 0
        self._misses = 0

    def _hash_prefix(self, tokens: list[int]) -> str:
        data = ",".join(map(str, tokens)).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def get(self, prefix_tokens: list[int]) -> dict[str, Any] | None:
        key = self._hash_prefix(prefix_tokens)
        val = self._cache.get(key)
        if val is not None:
            self._hits += 1
            return val
        self._misses += 1
        return None

    def put(self, prefix_tokens: list[int], kv_states: dict[str, Any]) -> None:
        if len(self._cache) >= self.max_entries:
            # Simple eviction
            first_key = next(iter(self._cache))
            del self._cache[first_key]
        key = self._hash_prefix(prefix_tokens)
        self._cache[key] = kv_states

    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
        }


prefix_kv_cache = PrefixKVCache()
