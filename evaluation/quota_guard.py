# -*- coding: utf-8 -*-
"""
quota_guard.py — Pre-flight quota estimation.

Before evaluation begins, estimates total API calls and tokens
needed. Warns if limits will be exceeded.
"""

from evaluation.config import (
    PROVIDERS,
    MAX_RULES_PER_BATCH,
    AVG_EVAL_INPUT_TOKENS,
    AVG_EVAL_OUTPUT_TOKENS,
    AVG_TURN_INPUT_TOKENS,
    AVG_TURN_OUTPUT_TOKENS,
    AVG_FEEDBACK_INPUT_TOKENS,
    AVG_FEEDBACK_OUTPUT_TOKENS,
)
from evaluation.rule_classifier import classify_rules


class QuotaEstimate:
    """Result of a pre-flight quota estimation."""

    def __init__(self):
        self.server_llm_calls = 0        # Conversation turns + feedback
        self.eval_llm_calls = 0          # LLM-as-judge calls
        self.total_llm_calls = 0
        self.deterministic_rules = 0
        self.pattern_rules = 0
        self.llm_rules = 0
        self.total_rules = 0
        self.estimated_tokens_in = 0
        self.estimated_tokens_out = 0
        self.estimated_cost_usd = 0.0
        self.warnings = []
        self.can_proceed = True

    def summary(self) -> dict:
        return {
            "server_llm_calls": self.server_llm_calls,
            "eval_llm_calls": self.eval_llm_calls,
            "total_llm_calls": self.total_llm_calls,
            "deterministic_rules": self.deterministic_rules,
            "pattern_rules": self.pattern_rules,
            "llm_rules": self.llm_rules,
            "total_rules": self.total_rules,
            "estimated_tokens_in": self.estimated_tokens_in,
            "estimated_tokens_out": self.estimated_tokens_out,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "warnings": self.warnings,
            "can_proceed": self.can_proceed,
        }

    def print_report(self):
        """Print a human-readable quota estimate."""
        print("\n" + "─" * 55)
        print("  PRE-FLIGHT QUOTA ESTIMATE")
        print("─" * 55)
        print(f"  Scenarios to run:        see below")
        print(f"  Server LLM calls:        {self.server_llm_calls}")
        print(f"  Evaluation LLM calls:    {self.eval_llm_calls}")
        print(f"  Total LLM calls:         {self.total_llm_calls}")
        print(f"  ─────────────────────────────────")
        print(f"  Rules evaluated by code: {self.deterministic_rules}")
        print(f"  Rules evaluated by regex:{self.pattern_rules}")
        print(f"  Rules evaluated by LLM:  {self.llm_rules}")
        print(f"  Total rules:             {self.total_rules}")
        print(f"  ─────────────────────────────────")
        print(f"  Est. input tokens:       ~{self.estimated_tokens_in:,}")
        print(f"  Est. output tokens:      ~{self.estimated_tokens_out:,}")
        print(f"  Est. cost (USD):         ${self.estimated_cost_usd:.4f}")

        if self.warnings:
            print(f"\n  ⚠ WARNINGS:")
            for w in self.warnings:
                print(f"    • {w}")
        else:
            print(f"\n  ✓ No quota warnings.")

        print(f"\n  Can proceed: {'✓ YES' if self.can_proceed else '✗ NO'}")
        print("─" * 55 + "\n")


def estimate_run(
    scenarios: list,
    rules_by_mode: dict,
) -> QuotaEstimate:
    """
    Estimate API usage before running evaluation.

    Parameters
    ----------
    scenarios : list
        List of scenario dicts with 'turns', 'rules_key' etc.
    rules_by_mode : dict
        The RULES_BY_MODE dictionary from test_framework.

    Returns
    -------
    QuotaEstimate
        Estimation with warnings if limits will be exceeded.
    """
    est = QuotaEstimate()

    total_turns = 0
    total_eval_batches = 0
    all_llm_rules = 0
    all_det_rules = 0
    all_pat_rules = 0

    for scenario in scenarios:
        n_turns = len(scenario.get("turns", []))
        total_turns += n_turns

        # Server-side: 1 LLM call per turn + 1 for feedback
        est.server_llm_calls += n_turns + 1

        # Evaluation: classify rules
        rules_key = scenario.get("rules_key", "")
        mode_rules = rules_by_mode.get(rules_key, {})

        for category in ["global", "escalation", "feedback"]:
            cat_rules = mode_rules.get(category, [])
            if not cat_rules:
                continue

            buckets = classify_rules(cat_rules)
            n_det = len(buckets["deterministic"])
            n_pat = len(buckets["pattern"])
            n_llm = len(buckets["llm"])

            all_det_rules += n_det
            all_pat_rules += n_pat
            all_llm_rules += n_llm

            # LLM eval batches needed (capped at MAX_RULES_PER_BATCH)
            if n_llm > 0:
                n_batches = (n_llm + MAX_RULES_PER_BATCH - 1) // MAX_RULES_PER_BATCH
                total_eval_batches += n_batches

    est.eval_llm_calls = total_eval_batches
    est.total_llm_calls = est.server_llm_calls + est.eval_llm_calls
    est.deterministic_rules = all_det_rules
    est.pattern_rules = all_pat_rules
    est.llm_rules = all_llm_rules
    est.total_rules = all_det_rules + all_pat_rules + all_llm_rules

    # Token estimates
    est.estimated_tokens_in = (
        total_turns * AVG_TURN_INPUT_TOKENS +
        len(scenarios) * AVG_FEEDBACK_INPUT_TOKENS +
        total_eval_batches * AVG_EVAL_INPUT_TOKENS
    )
    est.estimated_tokens_out = (
        total_turns * AVG_TURN_OUTPUT_TOKENS +
        len(scenarios) * AVG_FEEDBACK_OUTPUT_TOKENS +
        total_eval_batches * AVG_EVAL_OUTPUT_TOKENS
    )

    # Cost estimate (using primary provider rates)
    primary = PROVIDERS.get("groq", {})
    est.estimated_cost_usd = (
        primary.get("cost_per_1k_input", 0) * est.estimated_tokens_in / 1000 +
        primary.get("cost_per_1k_output", 0) * est.estimated_tokens_out / 1000
    )

    # Warnings
    for prov_name, prov_cfg in PROVIDERS.items():
        if not prov_cfg.get("enabled", False):
            continue
        rpd = prov_cfg.get("rpd_limit", 99999)
        if est.total_llm_calls > rpd * 0.5:
            est.warnings.append(
                f"{prov_name}: estimated {est.total_llm_calls} calls "
                f"vs {rpd} daily limit ({round(est.total_llm_calls/rpd*100)}%)"
            )

        rpm = prov_cfg.get("rpm_limit", 99999)
        # Estimate if we'll exceed RPM in burst
        if total_turns > rpm:
            est.warnings.append(
                f"{prov_name}: {total_turns} conversation turns may "
                f"exceed {rpm} RPM limit — expect delays"
            )

    if not any(PROVIDERS[p].get("enabled", False) for p in PROVIDERS):
        est.warnings.append("No LLM providers are enabled!")
        est.can_proceed = False

    return est
