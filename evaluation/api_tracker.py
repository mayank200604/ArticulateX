# -*- coding: utf-8 -*-
"""
api_tracker.py — Request and token tracking for evaluation runs.

Records every API call with provider, tokens, latency, and success/failure.
Provides per-scenario, per-category, and per-provider summaries.
"""

import time
from collections import defaultdict


class APITracker:
    """Tracks all API requests made during an evaluation run."""

    def __init__(self):
        self._records = []
        self._start_time = time.time()

    def record(
        self,
        provider: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        scenario: str = "",
        category: str = "",
        error: str = "",
    ):
        """Record a single API call."""
        self._records.append({
            "timestamp": time.time(),
            "provider": provider,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": round(latency_ms, 1),
            "success": success,
            "scenario": scenario,
            "category": category,
            "error": error,
        })

    @property
    def total_requests(self) -> int:
        return len(self._records)

    @property
    def successful_requests(self) -> int:
        return sum(1 for r in self._records if r["success"])

    @property
    def failed_requests(self) -> int:
        return sum(1 for r in self._records if not r["success"])

    @property
    def total_tokens_in(self) -> int:
        return sum(r["tokens_in"] for r in self._records)

    @property
    def total_tokens_out(self) -> int:
        return sum(r["tokens_out"] for r in self._records)

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_in + self.total_tokens_out

    @property
    def elapsed_seconds(self) -> float:
        return round(time.time() - self._start_time, 1)

    def summary(self) -> dict:
        """Overall summary across all providers."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens,
            "elapsed_seconds": self.elapsed_seconds,
            "cost_estimate_usd": self.cost_estimate(),
        }

    def per_provider(self) -> dict:
        """Breakdown by provider."""
        result = defaultdict(lambda: {
            "requests": 0, "success": 0, "failed": 0,
            "tokens_in": 0, "tokens_out": 0,
            "avg_latency_ms": 0.0, "errors": [],
        })
        for r in self._records:
            p = result[r["provider"]]
            p["requests"] += 1
            if r["success"]:
                p["success"] += 1
            else:
                p["failed"] += 1
                if r["error"]:
                    p["errors"].append(r["error"][:100])
            p["tokens_in"] += r["tokens_in"]
            p["tokens_out"] += r["tokens_out"]

        # Calculate avg latency
        for prov, data in result.items():
            latencies = [
                r["latency_ms"] for r in self._records
                if r["provider"] == prov and r["success"]
            ]
            if latencies:
                data["avg_latency_ms"] = round(
                    sum(latencies) / len(latencies), 1
                )
        return dict(result)

    def per_scenario(self) -> dict:
        """Breakdown by scenario."""
        result = defaultdict(lambda: {
            "requests": 0, "tokens_in": 0, "tokens_out": 0,
        })
        for r in self._records:
            s = result[r["scenario"] or "unknown"]
            s["requests"] += 1
            s["tokens_in"] += r["tokens_in"]
            s["tokens_out"] += r["tokens_out"]
        return dict(result)

    def per_category(self) -> dict:
        """Breakdown by rule category (global/escalation/feedback)."""
        result = defaultdict(lambda: {
            "requests": 0, "tokens_in": 0, "tokens_out": 0,
        })
        for r in self._records:
            c = result[r["category"] or "other"]
            c["requests"] += 1
            c["tokens_in"] += r["tokens_in"]
            c["tokens_out"] += r["tokens_out"]
        return dict(result)

    def cost_estimate(self) -> float:
        """Rough cost estimate in USD based on provider rates."""
        from evaluation.config import PROVIDERS
        total = 0.0
        for r in self._records:
            if not r["success"]:
                continue
            prov_cfg = PROVIDERS.get(r["provider"], {})
            cost_in = prov_cfg.get("cost_per_1k_input", 0) * r["tokens_in"] / 1000
            cost_out = prov_cfg.get("cost_per_1k_output", 0) * r["tokens_out"] / 1000
            total += cost_in + cost_out
        return round(total, 6)

    def to_dict(self) -> dict:
        """Full tracker data for JSON serialization."""
        return {
            "summary": self.summary(),
            "per_provider": self.per_provider(),
            "per_scenario": self.per_scenario(),
            "per_category": self.per_category(),
            "records": self._records,
        }
