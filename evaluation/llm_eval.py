# -*- coding: utf-8 -*-
"""
llm_eval.py — LLM-as-judge for subjective rules.

Only called for rules that genuinely require human-like judgment
(tone, warmth, coaching quality, etc.). All other rules are
handled by deterministic_eval.py and pattern_eval.py.

Batch cap: 15 rules per API call.
Keeps global/escalation/feedback as separate batches.
"""

import json
from typing import Optional

from evaluation.config import MAX_RULES_PER_BATCH
from evaluation.provider_manager import ProviderManager
from evaluation.cache import EvalCache


def _build_eval_prompt(
    rules: list[str],
    context_str: str,
    mode: str,
    level: int,
    category: str,
) -> str:
    """Build the evaluation prompt for a batch of subjective rules."""
    rules_formatted = ""
    for idx, r in enumerate(rules, 1):
        rules_formatted += f"{idx}. {r}\n"

    return f"""You are evaluating an AI communication coach application (ArticulateX).
Your job is to determine if the AI's responses or feedback followed specific rules during the session.

MODE: {mode}
LEVEL: {level}
CATEGORY: {category}

{context_str}

RULES TO EVALUATE:
{rules_formatted}

Determine if the AI followed each rule. For each rule:
1. The result must be exactly "PASS", "FAIL", or "PARTIAL".
2. The reason must be a concise, one-sentence explanation of why it passed, failed, or partially passed, referencing specific turns or quotes if relevant.
3. Confidence is your certainty in the judgment: 1.0 = certain, 0.5 = uncertain.

You MUST respond in JSON format with a single key "evaluations" containing a list of objects.
Each object must have the following fields:
- "rule": The exact text of the rule being evaluated (must match the rules listed above exactly)
- "result": "PASS", "FAIL", or "PARTIAL"
- "reason": A one-sentence explanation
- "confidence": A float between 0.0 and 1.0

Example JSON output structure:
{{
  "evaluations": [
    {{
      "rule": "AI must be warm and genuinely curious in tone",
      "result": "PASS",
      "reason": "The AI maintained a warm, curious tone throughout all turns.",
      "confidence": 0.9
    }}
  ]
}}"""


def _build_context_str(
    turns: list,
    category: str,
    feedback_text: str = "",
) -> str:
    """Build the context string for evaluation."""
    if category == "feedback":
        fb_truncated = feedback_text[:4000] if feedback_text else "(empty)"
        return f'FULL FEEDBACK REPORT:\n"""\n{fb_truncated}\n"""'

    elif category == "escalation":
        early = turns[:2]
        late = turns[4:6] if len(turns) >= 6 else turns[-2:]

        early_formatted = []
        for t in early:
            early_formatted.append(
                f"Turn {t['turn']}:\n"
                f"User: \"{t['user_input']}\"\n"
                f"AI: \"{t['ai_response']}\""
            )
        late_formatted = []
        for t in late:
            late_formatted.append(
                f"Turn {t['turn']}:\n"
                f"User: \"{t['user_input']}\"\n"
                f"AI: \"{t['ai_response']}\""
            )
        return (
            "EARLY TURNS OF SESSION:\n" + "\n\n".join(early_formatted) +
            "\n\nLATE TURNS OF SESSION:\n" + "\n\n".join(late_formatted)
        )

    else:
        # Global — format conversation turns
        turns_formatted = []
        for t in turns:
            turns_formatted.append(
                f"Turn {t['turn']}:\n"
                f"User: \"{t['user_input']}\"\n"
                f"AI: \"{t['ai_response']}\""
            )
        return "CONVERSATION TRANSCRIPT:\n" + "\n\n".join(turns_formatted)


def _parse_llm_response(
    raw_content: str,
    rules: list[str],
) -> list[dict]:
    """
    Parse the LLM evaluation response with recovery.

    Handles:
    - Valid JSON with "evaluations" key
    - Partial JSON (missing some rules)
    - Malformed JSON (returns UNKNOWN for all rules)
    """
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError:
        # JSON parse failure — return UNKNOWN for all
        print(f"  ⚠ LLM returned invalid JSON. Marking rules as UNKNOWN.")
        return [
            {
                "rule": r,
                "result": "UNKNOWN",
                "reason": "LLM returned malformed JSON response.",
                "eval_type": "llm",
                "confidence": 0.0,
            }
            for r in rules
        ]

    # Build lookup from LLM response
    evals_by_rule = {}
    for item in data.get("evaluations", []):
        rule_text = item.get("rule", "").strip()
        evals_by_rule[rule_text.lower()] = {
            "result": item.get("result", "UNKNOWN"),
            "reason": item.get("reason", ""),
            "confidence": item.get("confidence", 0.8),
        }

    # Match rules to LLM evaluations
    results = []
    for r in rules:
        r_clean = r.strip()
        match = evals_by_rule.get(r_clean.lower())

        if not match:
            # Substring/fuzzy match
            for k, v in evals_by_rule.items():
                if k in r_clean.lower() or r_clean.lower() in k:
                    match = v
                    break

        if match:
            results.append({
                "rule": r_clean,
                "result": match["result"],
                "reason": match["reason"],
                "eval_type": "llm",
                "confidence": match.get("confidence", 0.8),
            })
        else:
            results.append({
                "rule": r_clean,
                "result": "UNKNOWN",
                "reason": "Rule was not evaluated by LLM in batch response.",
                "eval_type": "llm",
                "confidence": 0.0,
            })

    return results


def evaluate_subjective_rules(
    rules: list[str],
    turns: list,
    mode: str,
    level: int,
    category: str,
    feedback_text: str = "",
    provider_manager: ProviderManager = None,
    cache: EvalCache = None,
    scenario: str = "",
) -> list[dict]:
    """
    Evaluate subjective rules using LLM-as-judge.

    - Batches rules in groups of MAX_RULES_PER_BATCH (15)
    - Checks cache before calling LLM
    - Uses provider_manager for rate-limited LLM calls
    - On LLM failure, marks rules as ERROR (no recursive fallback)

    Parameters
    ----------
    rules : list[str]
        List of subjective rule texts to evaluate.
    turns : list
        Conversation turn data.
    mode : str
        Evaluation mode (freestyle, debate1, etc.).
    level : int
        Difficulty level.
    category : str
        Rule category (global, escalation, feedback).
    feedback_text : str
        Feedback report text (for feedback category).
    provider_manager : ProviderManager
        Manages LLM provider selection and rate limiting.
    cache : EvalCache
        Evaluation result cache.
    scenario : str
        Scenario name for tracking.

    Returns
    -------
    list[dict]
        Evaluation results for each rule.
    """
    if not rules:
        return []

    if provider_manager is None:
        provider_manager = ProviderManager()

    all_results = []

    # Check cache for each rule first
    uncached_rules = []
    for rule in rules:
        if cache:
            # Build cache key from context
            context_key = _build_cache_context_key(
                turns, category, feedback_text
            )
            cached = cache.get(context_key, rule, mode, str(level), category)
            if cached:
                all_results.append(cached)
                continue
        uncached_rules.append(rule)

    if not uncached_rules:
        return all_results

    # Batch uncached rules in groups of MAX_RULES_PER_BATCH
    batches = []
    for i in range(0, len(uncached_rules), MAX_RULES_PER_BATCH):
        batches.append(uncached_rules[i:i + MAX_RULES_PER_BATCH])

    context_str = _build_context_str(turns, category, feedback_text)

    for batch_idx, batch in enumerate(batches):
        if len(batches) > 1:
            print(f"    Batch {batch_idx + 1}/{len(batches)} "
                  f"({len(batch)} rules)...")

        prompt = _build_eval_prompt(
            batch, context_str, mode, level, category,
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            raw_content = provider_manager.call(
                messages,
                json_mode=True,
                scenario=scenario,
                category=category,
            )
            batch_results = _parse_llm_response(raw_content, batch)

        except Exception as exc:
            print(f"  ✗ LLM batch evaluation failed: {exc}")
            # No recursive fallback — mark as ERROR
            batch_results = [
                {
                    "rule": r,
                    "result": "ERROR",
                    "reason": f"LLM evaluation failed: {str(exc)[:80]}",
                    "eval_type": "llm",
                    "confidence": 0.0,
                }
                for r in batch
            ]

        # Cache successful results
        if cache:
            context_key = _build_cache_context_key(
                turns, category, feedback_text
            )
            for result in batch_results:
                if result["result"] not in ("ERROR", "UNKNOWN"):
                    cache.set(
                        result,
                        context_key,
                        result["rule"],
                        mode,
                        str(level),
                        category,
                    )

        all_results.extend(batch_results)

    return all_results


def _build_cache_context_key(
    turns: list, category: str, feedback_text: str = ""
) -> str:
    """Build a cache-friendly context key from turns or feedback."""
    if category == "feedback":
        return (feedback_text or "")[:2000]
    elif category == "escalation":
        parts = []
        for t in (turns[:2] + turns[4:6] if len(turns) >= 6 else turns):
            parts.append(f"{t.get('ai_response', '')[:100]}")
        return "|".join(parts)
    else:
        parts = []
        for t in turns[:6]:
            parts.append(f"{t.get('ai_response', '')[:100]}")
        return "|".join(parts)
