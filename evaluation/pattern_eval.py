# -*- coding: utf-8 -*-
"""
pattern_eval.py — Regex and lightweight NLP rule evaluators.

Zero API calls. Uses pattern matching for rules that need
more than simple string checks but don't require LLM judgment.
"""

import re
from typing import Optional


def make_result(
    rule: str,
    result: str,
    reason: str,
    confidence: float = 0.85,
) -> dict:
    """Create a standardised evaluation result."""
    return {
        "rule": rule,
        "result": result,
        "reason": reason,
        "eval_type": "pattern",
        "confidence": confidence,
    }


# ════════════════════════════════════════════════════════════════
# CONTENT RESTRICTION PATTERNS
# ════════════════════════════════════════════════════════════════

# Patterns indicating grammar correction
GRAMMAR_CORRECTION_PATTERNS = [
    r"\byou (?:should|could|might) (?:say|use|write)\b",
    r"\bthe correct (?:word|phrase|form|way)\b",
    r"\binstead of (?:saying|using)\b",
    r"\bgrammatically\b",
    r"\bgrammar\b.*\b(?:fix|correct|improve|wrong|error)\b",
    r"\bthe (?:right|proper|correct) way to say\b",
    r"\byou meant to say\b",
    r"\byou should have said\b",
]

# Patterns indicating evidence/data demands
EVIDENCE_DEMAND_PATTERNS = [
    r"\b(?:give|provide|show|share|present|cite) (?:me )?(?:some |an? )?(?:evidence|data|statistics|stats|proof|research|study|studies|source|sources|numbers|figures|reference)\b",
    r"\bdo you have (?:any |some )?(?:evidence|data|statistics|proof|research|studies|sources)\b",
    r"\bwhat (?:evidence|data|statistics|research|studies|proof) (?:do you have|supports?)\b",
    r"\bback (?:it|that|this) up with (?:evidence|data|facts|numbers)\b",
    r"\bwhere (?:is|are) your (?:evidence|data|proof|sources)\b",
    r"\baccording to what (?:study|research|data)\b",
    r"\bcan you (?:cite|quote|reference)\b",
]

# Patterns indicating factual challenge
FACTUAL_CHALLENGE_PATTERNS = [
    r"\bthat(?:'s| is) (?:not |in)?(?:correct|accurate|true|right|factual)\b",
    r"\bactually,? (?:the )?(?:fact|truth|reality) is\b",
    r"\byou(?:'re| are) (?:wrong|incorrect|mistaken) about\b",
    r"\bthat claim is (?:false|untrue|incorrect|inaccurate)\b",
    r"\bthe (?:facts|evidence|research|data) (?:show|suggest|indicate|prove) otherwise\b",
]

# Patterns indicating intellectual judgment
INTELLECTUAL_JUDGMENT_PATTERNS = [
    r"\bthat(?:'s| is) (?:a )?(?:shallow|superficial|simplistic|naive|weak|poor|flawed) (?:argument|point|claim|reasoning|analysis|thinking)\b",
    r"\b(?:shallow|superficial|simplistic|naive|weak|poor|flawed).*(?:argument|point|claim|reasoning|analysis|thinking)\b",
    r"\byou(?:'re| are) not (?:thinking|reasoning) (?:deeply|critically|clearly) enough\b",
    r"\byour (?:argument|point|claim|reasoning|analysis) (?:lacks?|is missing|needs?) (?:depth|nuance|sophistication|rigor)\b",
    r"\bthat(?:'s| is) (?:too )?(?:basic|elementary|surface-level)\b",
]

# Patterns indicating filler mention (in non-feedback context)
FILLER_MENTION_PATTERNS = [
    r"\byou (?:said|used|keep saying|keep using) (?:'?um|uh|like|basically|you know)\b",
    r"\btoo many (?:fillers?|ums?|uhs?|likes?)\b",
    r"\bstop saying (?:um|uh|like|basically|you know)\b",
    r"\byour (?:filler|hesitation) (?:words?|sounds?|count)\b",
    r"\bfiller words?\b",
]

# Patterns indicating debate/argument in freestyle
DEBATE_LANGUAGE_PATTERNS = [
    r"\bi (?:disagree|challenge|push back|counter|reject|oppose)\b",
    r"\bthat(?:'s| is) (?:wrong|incorrect|not true|not right)\b",
    r"\byou(?:'re| are) (?:wrong|mistaken|incorrect)\b",
    r"\bdefend (?:your|that|this|the) (?:point|claim|argument|position)\b",
]

# Patterns indicating invented stats in feedback
INVENTED_STATS_PATTERNS = [
    r"\b(?:studies?|research) (?:show|suggest|indicate|prove|find|found)\b",
    r"\baccording to (?:a |the )?(?:study|research|survey|report)\b",
    r"\b\d{2,3}%\s+of\b",  # "73% of people..."
    r"\b(?:Harvard|Stanford|MIT|Oxford|Cambridge|Yale) (?:study|research|report)\b",
]

# Patterns for Indian English correction
INDIAN_ENGLISH_CORRECTION_PATTERNS = [
    r"\binstead of ['\"]?(?:prepone|do the needful|revert back|kindly)['\"]?\b",
    r"\b(?:prepone|do the needful|revert back) is (?:not |in)?correct\b",
    r"\b(?:prepone|do the needful|revert back) is (?:not |in)?(?:standard|proper) english\b",
    r"\bthat(?:'s| is) (?:not |in)?(?:standard|proper) english\b",
]

# Patterns indicating factual accuracy evaluation
FACTUAL_EVALUATION_PATTERNS = [
    r"\bfactually (?:incorrect|wrong|inaccurate|false)\b",
    r"\bthe facts? (?:don't|do not|doesn't|does not) support\b",
    r"\byour (?:facts?|claims?) (?:are|is) (?:wrong|incorrect|inaccurate)\b",
]

# Patterns indicating failure language
FAILURE_LANGUAGE_PATTERNS = [
    r"\bfundamental(?:ly)? (?:fail|flaw|weak|unable|incapable)\b",
    r"\bcomplete(?:ly)? (?:fail|unable|incapable|lost)\b",
    r"\bhopeless\b",
    r"\byou (?:can't|cannot|are unable to) communicate\b",
]

# Pattern for four-part feedback structure
FOUR_PART_MARKERS = ["POINT:", "REASON:", "EXAMPLE:", "TRY THIS INSTEAD:"]
FOUR_PART_MARKERS_ALT = ["POINT", "REASON", "EXAMPLE", "TRY THIS"]


# ════════════════════════════════════════════════════════════════
# EVALUATOR FUNCTIONS
# ════════════════════════════════════════════════════════════════

def _check_patterns(
    text: str, patterns: list[str], case_insensitive: bool = True
) -> list[str]:
    """Check text against a list of regex patterns. Returns matches."""
    flags = re.IGNORECASE if case_insensitive else 0
    matches = []
    for pat in patterns:
        found = re.findall(pat, text, flags)
        matches.extend(found)
    return matches


def eval_no_grammar_correction(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """AI must never correct grammar or vocabulary."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        matches = _check_patterns(ai, GRAMMAR_CORRECTION_PATTERNS)
        if matches:
            violations.append(
                f"Turn {t['turn']}: '{matches[0]}'"
            )
    if not violations:
        return [make_result(
            rule, "PASS",
            "No grammar corrections detected in AI responses.",
        )]
    return [make_result(
        rule, "FAIL",
        f"Grammar correction detected: {'; '.join(violations[:3])}",
    )]


def eval_no_indian_english_correction(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """AI must never correct Indian English expressions."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        matches = _check_patterns(ai, INDIAN_ENGLISH_CORRECTION_PATTERNS)
        if matches:
            violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    if not violations:
        return [make_result(rule, "PASS", "No Indian English corrections detected.")]
    return [make_result(
        rule, "FAIL",
        f"Indian English correction detected: {'; '.join(violations[:3])}",
    )]


def eval_no_evidence_demand(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """AI must never ask for data, statistics, evidence, or research."""
    text_to_check = feedback_text if feedback_text else ""
    violations = []

    if not feedback_text:
        # Check conversation turns
        for t in turns:
            ai = t.get("ai_response", "")
            matches = _check_patterns(ai, EVIDENCE_DEMAND_PATTERNS)
            if matches:
                violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    else:
        # Check feedback text
        matches = _check_patterns(feedback_text, EVIDENCE_DEMAND_PATTERNS)
        if matches:
            violations.append(f"Feedback: '{matches[0]}'")

    if not violations:
        return [make_result(rule, "PASS", "No evidence demands detected.")]
    return [make_result(
        rule, "FAIL",
        f"Evidence demand detected: {'; '.join(violations[:3])}",
    )]


def eval_no_factual_challenge(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """AI must never challenge whether argument is factually correct."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        matches = _check_patterns(ai, FACTUAL_CHALLENGE_PATTERNS)
        if matches:
            violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    if not violations:
        return [make_result(rule, "PASS", "No factual challenges detected.")]
    return [make_result(
        rule, "FAIL",
        f"Factual challenge detected: {'; '.join(violations[:3])}",
    )]


def eval_no_intellectual_judgment(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """AI must never judge intellectual strength of the point."""
    violations = []
    if not feedback_text:
        for t in turns:
            ai = t.get("ai_response", "")
            matches = _check_patterns(ai, INTELLECTUAL_JUDGMENT_PATTERNS)
            if matches:
                violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    else:
        matches = _check_patterns(feedback_text, INTELLECTUAL_JUDGMENT_PATTERNS)
        if matches:
            violations.append(f"Feedback: '{matches[0]}'")

    if not violations:
        return [make_result(rule, "PASS", "No intellectual judgments detected.")]
    return [make_result(
        rule, "FAIL",
        f"Intellectual judgment detected: {'; '.join(violations[:3])}",
    )]


def eval_no_filler_mention(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """AI must never mention fillers or delivery issues during turns."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        matches = _check_patterns(ai, FILLER_MENTION_PATTERNS)
        if matches:
            violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    if not violations:
        return [make_result(rule, "PASS", "No filler mentions detected.")]
    return [make_result(
        rule, "FAIL",
        f"Filler mention detected: {'; '.join(violations[:3])}",
    )]


def eval_no_debate_language(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """No debate or argument in freestyle mode."""
    violations = []
    for t in turns:
        ai = t.get("ai_response", "")
        matches = _check_patterns(ai, DEBATE_LANGUAGE_PATTERNS)
        if matches:
            violations.append(f"Turn {t['turn']}: '{matches[0]}'")
    if not violations:
        return [make_result(rule, "PASS", "No debate language detected.")]
    return [make_result(
        rule, "FAIL",
        f"Debate language detected: {'; '.join(violations[:3])}",
    )]


def eval_no_factual_evaluation(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """Feedback must never evaluate factual accuracy."""
    text = feedback_text or ""
    if not text:
        return [make_result(rule, "SKIP", "No feedback text to check.")]

    matches = _check_patterns(text, FACTUAL_EVALUATION_PATTERNS)
    if not matches:
        return [make_result(rule, "PASS", "No factual evaluation detected.")]
    return [make_result(
        rule, "FAIL",
        f"Factual evaluation in feedback: '{matches[0]}'",
    )]


def eval_no_invented_stats(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """THREE THINGS TO FIX must not contain invented statistics."""
    text = feedback_text or ""
    if not text:
        return [make_result(rule, "SKIP", "No feedback text to check.")]

    # Extract THREE THINGS TO FIX section
    section = ""
    lines = text.split("\n")
    in_section = False
    for line in lines:
        if "THREE THINGS TO FIX" in line.upper():
            in_section = True
            continue
        if in_section:
            # Stop at next section header
            if line.strip() and line.strip().isupper() and len(line.strip()) > 5:
                break
            section += line + "\n"

    if not section:
        section = text  # Check full text as fallback

    matches = _check_patterns(section, INVENTED_STATS_PATTERNS)
    if not matches:
        return [make_result(rule, "PASS", "No invented statistics found.")]
    return [make_result(
        rule, "FAIL",
        f"Possible invented stats in fixes: '{matches[0]}'",
        confidence=0.7,
    )]


def eval_simple_english(
    rule: str, turns: list, **kwargs,
) -> list[dict]:
    """AI must respond in simple clear English."""
    # Check for overly complex vocabulary or sentence structure
    violations = []
    complex_word_pattern = re.compile(r'\b[a-z]{15,}\b', re.IGNORECASE)
    for t in turns:
        ai = t.get("ai_response", "")
        long_words = complex_word_pattern.findall(ai)
        if len(long_words) >= 2:
            violations.append(
                f"Turn {t['turn']}: complex words {long_words[:2]}"
            )
    if not violations:
        return [make_result(rule, "PASS", "Responses use simple English.")]
    return [make_result(
        rule, "PARTIAL",
        f"Some complex language: {'; '.join(violations[:3])}",
        confidence=0.6,
    )]


def eval_four_part_structure(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """Each fix must follow four-part structure: POINT, REASON, EXAMPLE, TRY THIS INSTEAD."""
    text = feedback_text or ""
    if not text:
        return [make_result(rule, "SKIP", "No feedback text to check.")]

    text_upper = text.upper()
    found_markers = sum(
        1 for m in FOUR_PART_MARKERS if m.upper() in text_upper
    )

    if found_markers >= 3:
        return [make_result(
            rule, "PASS",
            f"Four-part structure detected ({found_markers}/4 markers found).",
        )]
    elif found_markers >= 2:
        return [make_result(
            rule, "PARTIAL",
            f"Partial structure ({found_markers}/4 markers found).",
            confidence=0.7,
        )]
    return [make_result(
        rule, "FAIL",
        f"Missing four-part structure ({found_markers}/4 markers found).",
    )]


def eval_no_failure_language(
    rule: str, turns: list,
    feedback_text: str = "", **kwargs,
) -> list[dict]:
    """Feedback must never use language implying fundamental failure."""
    text = feedback_text or ""
    if not text:
        return [make_result(rule, "SKIP", "No feedback text to check.")]

    matches = _check_patterns(text, FAILURE_LANGUAGE_PATTERNS)
    if not matches:
        return [make_result(rule, "PASS", "No failure language detected.")]
    return [make_result(
        rule, "FAIL",
        f"Failure language in feedback: '{matches[0]}'",
    )]


# ════════════════════════════════════════════════════════════════
# DISPATCHER
# ════════════════════════════════════════════════════════════════

EVALUATORS = {
    "eval_no_grammar_correction": eval_no_grammar_correction,
    "eval_no_indian_english_correction": eval_no_indian_english_correction,
    "eval_no_evidence_demand": eval_no_evidence_demand,
    "eval_no_factual_challenge": eval_no_factual_challenge,
    "eval_no_intellectual_judgment": eval_no_intellectual_judgment,
    "eval_no_filler_mention": eval_no_filler_mention,
    "eval_no_debate_language": eval_no_debate_language,
    "eval_no_factual_evaluation": eval_no_factual_evaluation,
    "eval_no_invented_stats": eval_no_invented_stats,
    "eval_simple_english": eval_simple_english,
    "eval_four_part_structure": eval_four_part_structure,
    "eval_no_failure_language": eval_no_failure_language,
}


def evaluate_pattern(
    rule: str,
    evaluator_name: str,
    turns: list,
    feedback_text: str = "",
) -> list[dict]:
    """
    Run a pattern evaluator by name.
    Returns list of result dicts.
    """
    func = EVALUATORS.get(evaluator_name)
    if not func:
        return [{
            "rule": rule,
            "result": "SKIP",
            "reason": f"No pattern evaluator found: {evaluator_name}",
            "eval_type": "pattern",
            "confidence": 0.0,
        }]
    return func(
        rule=rule, turns=turns, feedback_text=feedback_text,
    )
