# -*- coding: utf-8 -*-
"""
deterministic_eval.py — Code-only rule evaluators.

Zero API calls. Pure Python logic for rules that can be
evaluated deterministically from response text and metadata.
"""

import re
from typing import Optional


def make_result(
    rule: str,
    result: str,
    reason: str,
    confidence: float = 1.0,
) -> dict:
    """Create a standardised evaluation result."""
    return {
        "rule": rule,
        "result": result,       # PASS / FAIL / PARTIAL / SKIP
        "reason": reason,
        "eval_type": "deterministic",
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════
# SENTENCE COUNT EVALUATORS
# ════════════════════════════════════════════════════════════════

def _count_sentences(text: str) -> int:
    """Count sentences in text using punctuation boundaries."""
    if not text or not text.strip():
        return 0
    # Split on sentence-ending punctuation followed by space or end
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # Filter empty and count
    sentences = [s.strip() for s in parts if s.strip()]
    # If no sentence-ending punct found, the whole text is one sentence
    return max(len(sentences), 1)


def eval_sentence_count_1_2(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """AI response must be 1-2 sentences maximum."""
    results = []
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        count = _count_sentences(ai)
        if count > 2:
            violations.append(
                f"Turn {t['turn']}: {count} sentences"
            )
    if not violations:
        results.append(make_result(
            rule, "PASS",
            "All responses were 1-2 sentences.",
        ))
    else:
        results.append(make_result(
            rule, "FAIL",
            f"Exceeded 2 sentences: {'; '.join(violations[:3])}",
        ))
    return results


def eval_sentence_count_2_3(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """Maximum 2-3 sentences per response."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        count = _count_sentences(ai)
        if count > 3:
            violations.append(
                f"Turn {t['turn']}: {count} sentences"
            )
    if not violations:
        return [make_result(
            rule, "PASS",
            "All responses were within 2-3 sentences.",
        )]
    return [make_result(
        rule, "FAIL",
        f"Exceeded 3 sentences: {'; '.join(violations[:3])}",
    )]


# ════════════════════════════════════════════════════════════════
# BANNED PHRASE EVALUATOR
# ════════════════════════════════════════════════════════════════

BANNED_PHRASES = [
    "great point", "excellent", "well argued", "good point",
    "well done", "interesting", "that said", "however",
    "perfectly said",
]


def eval_banned_phrases(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """AI must never use banned phrases."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "").lower()
        for phrase in BANNED_PHRASES:
            if phrase in ai:
                violations.append(
                    f"Turn {t['turn']}: '{phrase}'"
                )
    if not violations:
        return [make_result(
            rule, "PASS",
            "No banned phrases found in any response.",
        )]
    return [make_result(
        rule, "FAIL",
        f"Banned phrases used: {'; '.join(violations[:5])}",
    )]


# ════════════════════════════════════════════════════════════════
# SENTENCE STARTER VARIETY
# ════════════════════════════════════════════════════════════════

def _first_word(text: str) -> str:
    """Extract the first word of a response, lowercased."""
    words = text.strip().split()
    return words[0].lower().rstrip(".,!?:;") if words else ""


def eval_sentence_starter_variety(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """Never start two consecutive responses the same way."""
    violations = []
    prev_starter = ""
    for t in turns:
        ai = t.get("ai_response", "")
        starter = _first_word(ai)
        if starter and starter == prev_starter:
            violations.append(
                f"Turn {t['turn']}: repeated starter '{starter}'"
            )
        prev_starter = starter

    if not violations:
        return [make_result(
            rule, "PASS",
            "All consecutive responses have different starters.",
        )]
    return [make_result(
        rule, "FAIL",
        f"Repeated starters: {'; '.join(violations[:3])}",
    )]


# ════════════════════════════════════════════════════════════════
# QUESTION COUNT
# ════════════════════════════════════════════════════════════════

def eval_exactly_one_question(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """AI must ask exactly ONE follow-up question per turn."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        q_count = ai.count("?")
        if q_count == 0:
            violations.append(f"Turn {t['turn']}: no question")
        elif q_count > 1:
            violations.append(
                f"Turn {t['turn']}: {q_count} questions"
            )

    if not violations:
        return [make_result(
            rule, "PASS",
            "Exactly one question per turn in all responses.",
        )]

    # Partial if most turns are correct
    fail_rate = len(violations) / max(len(turns), 1)
    result = "FAIL" if fail_rate > 0.5 else "PARTIAL"
    return [make_result(
        rule, result,
        f"Question count issues: {'; '.join(violations[:3])}",
        confidence=0.9,
    )]


# ════════════════════════════════════════════════════════════════
# INTERRUPT EVALUATORS
# ════════════════════════════════════════════════════════════════

def eval_zero_interrupts(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """Zero interruptions — interrupt probability is 0.0."""
    interrupts = [
        t for t in turns if t.get("is_interrupt", False)
    ]
    if not interrupts:
        return [make_result(
            rule, "PASS",
            "No interruptions occurred.",
        )]
    return [make_result(
        rule, "FAIL",
        f"{len(interrupts)} interruption(s) occurred at turns: "
        f"{[t['turn'] for t in interrupts]}",
    )]


def eval_interrupt_rate(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """Interrupt probability check (statistical, soft pass)."""
    # This is probabilistic — we can only check it's roughly right
    return [make_result(
        rule, "SKIP",
        "Interrupt probability is stochastic — cannot verify deterministically.",
        confidence=0.0,
    )]


def eval_interrupt_variation(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """Interrupt phrases must vary — never repeat same opener twice in a row."""
    interrupt_turns = [
        t for t in turns if t.get("is_interrupt", False)
    ]
    if len(interrupt_turns) < 2:
        return [make_result(
            rule, "PASS",
            "Fewer than 2 interrupts — variation not applicable.",
        )]

    violations = []
    for i in range(1, len(interrupt_turns)):
        prev = _first_word(interrupt_turns[i-1].get("ai_response", ""))
        curr = _first_word(interrupt_turns[i].get("ai_response", ""))
        if prev and prev == curr:
            violations.append(
                f"Turns {interrupt_turns[i-1]['turn']}-{interrupt_turns[i]['turn']}: "
                f"repeated '{curr}'"
            )

    if not violations:
        return [make_result(rule, "PASS", "Interrupt openers varied.")]
    return [make_result(
        rule, "FAIL",
        f"Repeated interrupt openers: {'; '.join(violations[:3])}",
    )]


# ════════════════════════════════════════════════════════════════
# STRATEGY BAN EVALUATORS
# ════════════════════════════════════════════════════════════════

def eval_strategy_not_used(
    rule: str, turns: list, **kwargs
) -> list[dict]:
    """
    Strategy ban rules. These are enforced by the server code itself
    (unpredictability.py). We mark them as SKIP since the test framework
    doesn't track strategy choices (they're server-internal).
    """
    return [make_result(
        rule, "SKIP",
        "Strategy enforcement is server-internal. "
        "Cannot verify from conversation transcript.",
        confidence=0.0,
    )]


# ════════════════════════════════════════════════════════════════
# FEEDBACK STRUCTURE EVALUATORS
# ════════════════════════════════════════════════════════════════

def eval_feedback_banned_phrase(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """Check that feedback doesn't contain specific banned phrases."""
    if not feedback_text:
        return [make_result(rule, "SKIP", "No feedback text available.")]

    # Extract the banned phrase from the rule text
    text_lower = feedback_text.lower()
    rule_lower = rule.lower()

    # Try to extract the quoted phrase from the rule
    banned = None
    for pattern in [r"'([^']+)'", r'"([^"]+)"']:
        match = re.search(pattern, rule_lower)
        if match:
            banned = match.group(1)
            break

    if not banned:
        # Fallback: extract after "never say" or "never start with"
        for prefix in ["never say ", "never soften with ",
                        "never start with "]:
            if prefix in rule_lower:
                banned = rule_lower.split(prefix, 1)[1].strip("'\"")
                break

    if not banned:
        return [make_result(
            rule, "SKIP",
            "Could not extract banned phrase from rule text.",
        )]

    if banned in text_lower:
        return [make_result(
            rule, "FAIL",
            f"Feedback contains banned phrase: '{banned}'",
        )]
    return [make_result(
        rule, "PASS",
        f"Feedback does not contain '{banned}'.",
    )]


def eval_feedback_has_section(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """Check that required sections exist in feedback."""
    if not feedback_text:
        return [make_result(rule, "SKIP", "No feedback text available.")]

    rule_lower = rule.lower()
    text_upper = feedback_text.upper()

    if "one earned encouragement" in rule_lower:
        if "ENCOURAGEMENT" in text_upper or "EARNED" in text_upper:
            return [make_result(
                rule, "PASS",
                "Feedback contains an encouragement section.",
            )]
        return [make_result(
            rule, "FAIL",
            "No earned encouragement section found in feedback.",
        )]

    return [make_result(rule, "SKIP", "Section check not applicable.")]


# ════════════════════════════════════════════════════════════════
# FILLER OVERRIDE EVALUATORS
# ════════════════════════════════════════════════════════════════

def eval_filler_override(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """Filler-based strategy override — server-internal."""
    return [make_result(
        rule, "SKIP",
        "Filler override triggers are server-internal. "
        "Cannot verify from transcript.",
        confidence=0.0,
    )]


# ════════════════════════════════════════════════════════════════
# SKIP EVALUATOR (for rules that can't be tested)
# ════════════════════════════════════════════════════════════════

def eval_skip(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """Rules that are configuration-level, not behavioural."""
    return [make_result(
        rule, "SKIP",
        "This rule is a configuration setting, not a behavioural check.",
        confidence=0.0,
    )]


# ════════════════════════════════════════════════════════════════
# DISPATCHER
# ════════════════════════════════════════════════════════════════

EVALUATORS = {
    "eval_sentence_count_1_2": eval_sentence_count_1_2,
    "eval_sentence_count_2_3": eval_sentence_count_2_3,
    "eval_banned_phrases": eval_banned_phrases,
    "eval_sentence_starter_variety": eval_sentence_starter_variety,
    "eval_exactly_one_question": eval_exactly_one_question,
    "eval_zero_interrupts": eval_zero_interrupts,
    "eval_interrupt_rate": eval_interrupt_rate,
    "eval_interrupt_variation": eval_interrupt_variation,
    "eval_strategy_not_used": eval_strategy_not_used,
    "eval_feedback_banned_phrase": eval_feedback_banned_phrase,
    "eval_feedback_has_section": eval_feedback_has_section,
    "eval_filler_override": eval_filler_override,
    "eval_skip": eval_skip,
}


def evaluate_deterministic(
    rule: str,
    evaluator_name: str,
    turns: list,
    feedback_text: str = "",
) -> list[dict]:
    """
    Run a deterministic evaluator by name.
    Returns list of result dicts.
    """
    func = EVALUATORS.get(evaluator_name)
    if not func:
        return [make_result(
            rule, "SKIP",
            f"No deterministic evaluator found: {evaluator_name}",
        )]
    return func(
        rule=rule, turns=turns, feedback_text=feedback_text,
    )
