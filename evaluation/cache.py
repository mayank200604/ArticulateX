# -*- coding: utf-8 -*-
"""
cache.py — Evaluation result caching.

SHA256-based cache that maps (prompt + user_input + ai_response + rule)
to evaluation results. Only caches LLM evaluations since deterministic
and pattern evaluators are already fast.
"""

import os
import json
import hashlib
from typing import Optional


class EvalCache:
    """
    SHA256-based evaluation cache.
    Persists to disk as JSON for reuse across runs.
    """

    def __init__(self, cache_path: str = None):
        from evaluation.config import CACHE_FILE
        self.cache_path = cache_path or CACHE_FILE
        self._cache = {}
        self._hits = 0
        self._misses = 0
        self._load_from_disk()

    @staticmethod
    def _make_key(*parts: str) -> str:
        """Create a SHA256 cache key from input parts."""
        combined = "|||".join(str(p) for p in parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def get(self, *key_parts: str) -> Optional[dict]:
        """
        Look up a cached evaluation result.

        Parameters: variable parts used to form the key,
        e.g., (ai_response, rule_text, category, mode)

        Returns: cached result dict or None
        """
        key = self._make_key(*key_parts)
        result = self._cache.get(key)
        if result is not None:
            self._hits += 1
            return result
        self._misses += 1
        return None

    def set(self, result: dict, *key_parts: str):
        """Store an evaluation result in the cache."""
        key = self._make_key(*key_parts)
        self._cache[key] = result

    def save_to_disk(self):
        """Persist cache to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"  ⚠ Cache save failed: {exc}")

    def _load_from_disk(self):
        """Load cache from disk if it exists."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def clear(self):
        """Clear all cached results."""
        self._cache = {}
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 3) if total > 0 else 0.0

    def stats(self) -> dict:
        return {
            "cache_size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
        }
