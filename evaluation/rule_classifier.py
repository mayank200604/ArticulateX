# -*- coding: utf-8 -*-
"""
rule_classifier.py — Classifies every rule into evaluation tiers.

Tier 1: deterministic — evaluated by code only (zero API calls)
Tier 2: pattern     — evaluated by regex / NLP (zero API calls)
Tier 3: llm         — evaluated by LLM-as-judge (API call required)

Each rule is mapped by its exact text to a tier and an evaluator function name.
"""

from typing import Literal

RuleType = Literal["deterministic", "pattern", "llm"]


# ════════════════════════════════════════════════════════════════
# RULE CLASSIFICATION MAP
#
# Keys: normalised rule text (lowercase, stripped)
# Values: (type, evaluator_function_name)
# ════════════════════════════════════════════════════════════════

RULE_CLASSIFICATIONS: dict[str, tuple[RuleType, str]] = {

    # ── DETERMINISTIC: sentence / word count ─────────────────────
    "ai response must be 1-2 sentences maximum":
        ("deterministic", "eval_sentence_count_1_2"),
    "ai must respond in simple clear english":
        ("pattern", "eval_simple_english"),
    "maximum 2-3 sentences per response":
        ("deterministic", "eval_sentence_count_2_3"),
    "ai response must be 1-2 sentences":
        ("deterministic", "eval_sentence_count_1_2"),

    # ── DETERMINISTIC: banned phrases ────────────────────────────
    "ai must never use banned phrases: great point / excellent / "
    "well argued / good point / well done / interesting / "
    "that said / however / perfectly said":
        ("deterministic", "eval_banned_phrases"),
    "ai must never use banned phrases: great point / excellent / "
    "well argued / good point / well done / interesting":
        ("deterministic", "eval_banned_phrases"),

    # ── DETERMINISTIC: sentence starter variety ──────────────────
    "ai must vary sentence starter every turn — never start "
    "two consecutive responses the same way":
        ("deterministic", "eval_sentence_starter_variety"),
    "vary sentence starter every turn — never start two "
    "consecutive responses the same way":
        ("deterministic", "eval_sentence_starter_variety"),
    "ai must vary sentence starter every turn":
        ("deterministic", "eval_sentence_starter_variety"),
    "vary sentence starter every turn":
        ("deterministic", "eval_sentence_starter_variety"),

    # ── DETERMINISTIC: question count ────────────────────────────
    "ai must ask exactly one follow-up question per turn":
        ("deterministic", "eval_exactly_one_question"),
    "ai must ask one specific follow-up question about something "
    "the user mentioned":
        ("deterministic", "eval_exactly_one_question"),

    # ── DETERMINISTIC: interrupts ────────────────────────────────
    "zero interruptions — interrupt probability is 0.0":
        ("deterministic", "eval_zero_interrupts"),

    # ── DETERMINISTIC: strategy bans (checked from metadata) ─────
    "demand_one_sentence strategy is completely banned in level 1":
        ("deterministic", "eval_strategy_not_used"),
    "push_back_hard strategy is completely banned in level 1":
        ("deterministic", "eval_strategy_not_used"),
    "interrupt_redirect strategy is completely banned in level 1":
        ("deterministic", "eval_strategy_not_used"),
    "change_topic strategy is completely banned in level 1":
        ("deterministic", "eval_strategy_not_used"),
    "misunderstand strategy is completely banned in level 1":
        ("deterministic", "eval_strategy_not_used"),
    "turn 1-2 also bans devils_advocate and ask_for_evidence":
        ("deterministic", "eval_strategy_not_used"),
    "no demand for one sentence on turn 1 regardless of level":
        ("deterministic", "eval_strategy_not_used"),
    "no ask_to_repeat on turn 1 regardless of level":
        ("deterministic", "eval_strategy_not_used"),
    "no demand for one sentence when user spoke 30+ words":
        ("deterministic", "eval_strategy_not_used"),
    "no ask_to_repeat when user spoke 30+ words":
        ("deterministic", "eval_strategy_not_used"),
    "demand_one_sentence banned in first 2 turns for level 2":
        ("deterministic", "eval_strategy_not_used"),
    "demand_one_sentence never repeats within 5 turns":
        ("deterministic", "eval_strategy_not_used"),
    "demand_one_sentence never repeats within 3 turns in level 3":
        ("deterministic", "eval_strategy_not_used"),
    "demand_one_sentence banned on turn 1":
        ("deterministic", "eval_strategy_not_used"),
    "change_topic fires exactly on turn 3 (guaranteed)":
        ("deterministic", "eval_strategy_not_used"),

    # ── DETERMINISTIC: feedback banned phrases ───────────────────
    "feedback must never say 'hesitant and unclear communicator'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "feedback must never say 'struggles to convey'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "feedback must never say 'lacks conviction'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "feedback must never say 'showed potential'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "feedback must never say 'willingness to engage'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "feedback must never say 'good attempt'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "overall verdict must never start with 'hesitant and unclear'":
        ("deterministic", "eval_feedback_banned_phrase"),
    "overall verdict must never soften with 'showed potential'":
        ("deterministic", "eval_feedback_banned_phrase"),

    # ── DETERMINISTIC: feedback structure ─────────────────────────
    "one earned encouragement is mandatory":
        ("deterministic", "eval_feedback_has_section"),
    "three things to fix must not contain invented statistics "
    "or research references":
        ("pattern", "eval_no_invented_stats"),

    # ── PATTERN: content restrictions ────────────────────────────
    "ai must never correct grammar or vocabulary":
        ("pattern", "eval_no_grammar_correction"),
    "ai must never correct indian english expressions":
        ("pattern", "eval_no_indian_english_correction"),
    "ai must never ask for data, statistics, evidence, or research":
        ("pattern", "eval_no_evidence_demand"),
    "ai must never challenge whether argument is factually correct":
        ("pattern", "eval_no_factual_challenge"),
    "ai must never judge intellectual strength of the point":
        ("pattern", "eval_no_intellectual_judgment"),
    "ai must never mention fillers or delivery issues during turns":
        ("pattern", "eval_no_filler_mention"),
    "no debate or argument in freestyle mode":
        ("pattern", "eval_no_debate_language"),
    "there is no right or wrong answer in freestyle":
        ("llm", "eval_subjective"),
    "feedback must never evaluate factual accuracy of argument":
        ("pattern", "eval_no_factual_evaluation"),
    "feedback must never evaluate factual accuracy":
        ("pattern", "eval_no_factual_evaluation"),
    "feedback must never ask for strong evidence":
        ("pattern", "eval_no_evidence_demand"),
    "feedback must never demand evidence or data":
        ("pattern", "eval_no_evidence_demand"),
    "feedback must never judge intellectual depth of point":
        ("pattern", "eval_no_intellectual_judgment"),
    "ai must encourage user to use simple english":
        ("llm", "eval_subjective"),
    "ai must never challenge the user's interpretation":
        ("llm", "eval_subjective"),

    # ── PATTERN: feedback content ────────────────────────────────
    "three things to fix: minimum 2 out of 3 must be "
    "communication fixes":
        ("llm", "eval_subjective"),
    "each fix must follow four-part structure: "
    "point, reason, example, try this instead":
        ("pattern", "eval_four_part_structure"),

    # ── PATTERN: interrupt variation ─────────────────────────────
    "interrupt phrases must vary — never repeat same opener "
    "twice in a row":
        ("deterministic", "eval_interrupt_variation"),

    # ── PATTERN: tone triggers ───────────────────────────────────
    "say-it-again fires when total fillers exceed 5 "
    "(demand_one_sentence override)":
        ("deterministic", "eval_filler_override"),
    "just_did_redo triggers when fillers > 5 at level 3":
        ("deterministic", "eval_filler_override"),

    # ── LLM: subjective tone / quality ───────────────────────────
    "ai must keep the user speaking comfortably":
        ("llm", "eval_subjective"),
    "ai must be warm and genuinely curious in tone":
        ("llm", "eval_subjective"),
    "ai must never challenge, correct, or evaluate content":
        ("llm", "eval_subjective"),
    "ai must sound like a real person, not a robot":
        ("llm", "eval_subjective"),
    "sound like a real person not a robot":
        ("llm", "eval_subjective"),
    "ai must acknowledge what the user said briefly and genuinely":
        ("llm", "eval_subjective"),
    "follow-up must connect to what user actually said — "
    "not a generic question":
        ("llm", "eval_subjective"),
    "ai must react curiously and playfully to what user said":
        ("llm", "eval_subjective"),
    "conversation should feel like two people exploring "
    "something strange together":
        ("llm", "eval_subjective"),
    "ai must never evaluate content quality":
        ("llm", "eval_subjective"),
    "goal is spontaneous speech — anything goes":
        ("llm", "eval_subjective"),
    "no correct answer — no topic to stay on":
        ("llm", "eval_subjective"),
    "tone must be curious and playful":
        ("llm", "eval_subjective"),

    # ── LLM: debate level-specific behaviour ─────────────────────
    "ai's job is to keep the user speaking — fluency is everything":
        ("llm", "eval_subjective"),
    "if user spoke fluently and finished thought: respond warmly "
    "and ask one simple follow-up":
        ("llm", "eval_subjective"),
    "if user trailed off: prompt to finish that thought":
        ("llm", "eval_subjective"),
    "if user used many fillers: note it once gently then move on — "
    "never block progress":
        ("llm", "eval_subjective"),
    "if user lost their thread: ask where they were going with that":
        ("llm", "eval_subjective"),
    "never make the user feel wrong or stuck":
        ("llm", "eval_subjective"),
    "never block the user from continuing":
        ("llm", "eval_subjective"),
    "content check: only check if user is on topic":
        ("llm", "eval_subjective"),
    "any on-topic point is acceptable — simple or complex, "
    "strong or weak":
        ("llm", "eval_subjective"),
    "only call out content if completely off-topic":
        ("llm", "eval_subjective"),
    "never ask user to be more specific about content in level 1":
        ("llm", "eval_subjective"),
    "tone: warm debate partner, firm but never harsh":
        ("llm", "eval_subjective"),

    # ── LLM: anti-sycophancy ─────────────────────────────────────
    "anti-sycophancy: never validate just because user repeated "
    "point more confidently":
        ("llm", "eval_subjective"),
    "anti-sycophancy at maximum: never validate just because "
    "user repeated point more confidently":
        ("llm", "eval_subjective"),
    "if user changed position without reasoning — call it out":
        ("llm", "eval_subjective"),
    "position change without reasoning — call it out every time":
        ("llm", "eval_subjective"),
    "position change without reasoning — call it out every time "
    "not just once":
        ("llm", "eval_subjective"),
    "never let a communication weakness pass because user "
    "seems frustrated or tired":
        ("llm", "eval_subjective"),
    "if delivery flaw existed — flaw still exists even if user "
    "sounds more confident now":
        ("llm", "eval_subjective"),

    # ── LLM: 70/30 rule ─────────────────────────────────────────
    "70/30 rule: 70% communication quality, 30% content relevance":
        ("llm", "eval_subjective"),

    # ── LLM: Level 2 specific ────────────────────────────────────
    "firmer than level 1 — firm and direct from turn 1":
        ("llm", "eval_subjective"),
    "no warmup and no encouragement mid-turn":
        ("llm", "eval_subjective"),
    "if unclear: challenge with 'i followed the words but not "
    "the point — say it more directly'":
        ("llm", "eval_subjective"),
    "if user agreed too quickly: 'you just changed your position "
    "— what do you actually believe?'":
        ("llm", "eval_subjective"),
    "if user lost thread: 'you started on x and ended on y — "
    "which is your argument?'":
        ("llm", "eval_subjective"),
    "if user held position well: push back harder to test "
    "if they can maintain it":
        ("llm", "eval_subjective"),
    "if user repeated same point: 'you already said that — "
    "go deeper'":
        ("llm", "eval_subjective"),
    "vary the challenge every single turn":
        ("llm", "eval_subjective"),
    "vague on-topic points get precision challenge — "
    "'what specifically makes it so?' (not knowledge demand)":
        ("llm", "eval_subjective"),
    "off-topic: redirect clearly and immediately":
        ("llm", "eval_subjective"),
    "specific on-topic claim: accept it and challenge "
    "communication quality around it instead":
        ("llm", "eval_subjective"),
    "interrupt probability is 20-22% per turn":
        ("deterministic", "eval_interrupt_rate"),
    "pause warning at 3 seconds":
        ("deterministic", "eval_skip"),
    "ai picks topic in level 2":
        ("deterministic", "eval_skip"),
    "ai picks topic in level 3":
        ("deterministic", "eval_skip"),
    "side is randomly assigned (user_picks_side is false)":
        ("deterministic", "eval_skip"),

    # ── LLM: Level 3 specific ────────────────────────────────────
    "immediate aggression from turn 1 — no warmup":
        ("llm", "eval_subjective"),
    "every turn has pressure — no exceptions":
        ("llm", "eval_subjective"),
    "hedging challenged immediately: 'you said i think maybe — "
    "pick one. do you believe this or not?'":
        ("llm", "eval_subjective"),
    "backed down called out: 'you started on one side and just "
    "agreed with me — what happened to your argument?'":
        ("llm", "eval_subjective"),
    "rambling called out: 'too long. one point. say it again.'":
        ("llm", "eval_subjective"),
    "trailing off called out: 'you did not finish. finish it.'":
        ("llm", "eval_subjective"),
    "good clear delivery still gets pressure: 'faster. say it "
    "in half the words.'":
        ("llm", "eval_subjective"),
    "strong position gets pushback: 'you said that — i "
    "completely disagree. defend it.'":
        ("llm", "eval_subjective"),
    "vague on-topic claim: precision challenge — 'what "
    "specifically is harmful? be precise.'":
        ("llm", "eval_subjective"),
    "point drifted across turns: 'your point in turn 2 and "
    "your point now are different things — which is your "
    "actual argument?'":
        ("llm", "eval_subjective"),
    "off-topic: called out sharply and immediately":
        ("llm", "eval_subjective"),
    "specific clear claim: force user to hold it and defend it "
    "under maximum pressure":
        ("llm", "eval_subjective"),
    "tone: relentless, aggressive but not rude":
        ("llm", "eval_subjective"),
    "interrupt probability is 50% per turn":
        ("deterministic", "eval_interrupt_rate"),
    "pause terminates at 2 seconds — no warning":
        ("deterministic", "eval_skip"),

    # ── LLM: escalation rules ────────────────────────────────────
    "turn 1-2: keep it very light":
        ("llm", "eval_subjective"),
    "turn 3+: slightly more engaged but still gentle":
        ("llm", "eval_subjective"),
    "difficulty increases gradually turn by turn":
        ("llm", "eval_subjective"),
    "turn 8+: let user wrap up — ban devils_advocate, "
    "ask_for_evidence, sharp_followup":
        ("deterministic", "eval_strategy_not_used"),
    "turn 1-2: firm":
        ("llm", "eval_subjective"),
    "turn 3-4: firm and pushing":
        ("llm", "eval_subjective"),
    "turn 5+: maximum level 2 pressure":
        ("llm", "eval_subjective"),

    # ── LLM: feedback quality ────────────────────────────────────
    "feedback harshness is 2 out of 10":
        ("llm", "eval_subjective"),
    "feedback harshness: 3 out of 10":
        ("llm", "eval_subjective"),
    "feedback harshness: 6 out of 10":
        ("llm", "eval_subjective"),
    "feedback harshness: 10 out of 10 — zero softening":
        ("llm", "eval_subjective"),
    "overall verdict must be positive or neutral only":
        ("llm", "eval_subjective"),
    "what worked must find at least 2 genuine things":
        ("llm", "eval_subjective"),
    "what worked must find at least 1-2 genuine communication "
    "positives — even small things count":
        ("llm", "eval_subjective"),
    "three things to fix must be simple, kind, achievable":
        ("llm", "eval_subjective"),
    "three things to fix must focus on fluency and flow only":
        ("llm", "eval_subjective"),
    "three things to fix must never mention content quality "
    "or argument strength":
        ("llm", "eval_subjective"),
    "be honest but never crushing":
        ("llm", "eval_subjective"),
    "overall verdict must acknowledge effort and identify "
    "one main thing to work on":
        ("llm", "eval_subjective"),
    "three things to fix must be simple and achievable":
        ("llm", "eval_subjective"),
    "three things to fix must all be communication-based — "
    "never about content strength":
        ("llm", "eval_subjective"),
    "one earned encouragement is mandatory — must be specific "
    "and real":
        ("llm", "eval_subjective"),
    "feedback must never use language implying fundamental failure":
        ("pattern", "eval_no_failure_language"),
    "honest and direct — no softening, no cruelty":
        ("llm", "eval_subjective"),
    "overall verdict is honest assessment — not encouraging, "
    "not crushing, factual":
        ("llm", "eval_subjective"),
    "what worked only if genuinely good — be selective":
        ("llm", "eval_subjective"),
    "three things to fix more demanding than level 1":
        ("llm", "eval_subjective"),
    "three things to fix: at least one fix about structure "
    "or holding position":
        ("llm", "eval_subjective"),
    "one earned encouragement only if deserved — skip if "
    "performance was average throughout":
        ("llm", "eval_subjective"),
    "treat user like a professional under evaluation":
        ("llm", "eval_subjective"),
    "overall verdict reflects level 3 standards — mediocre "
    "performance is called mediocre directly":
        ("llm", "eval_subjective"),
    "what worked: only if genuinely strong — if nothing was "
    "genuinely strong write 'nothing in this session stood "
    "out at level 3 standards'":
        ("llm", "eval_subjective"),
    "three things to fix must be demanding and specific":
        ("llm", "eval_subjective"),
    "three things to fix must quote exact turn numbers and "
    "exact words":
        ("llm", "eval_subjective"),
    "three things to fix: at least one fix about confidence "
    "under pressure":
        ("llm", "eval_subjective"),
    "one earned encouragement only if performance was "
    "objectively strong — if not skip entirely and write "
    "'no standout moment this session'":
        ("llm", "eval_subjective"),
    "feedback must never use any verdict that could apply "
    "to level 1":
        ("llm", "eval_subjective"),
}


def classify_rule(rule_text: str) -> tuple[RuleType, str]:
    """
    Classify a rule into its evaluation tier.

    Returns (rule_type, evaluator_function_name).
    Falls back to ("llm", "eval_subjective") for unknown rules.
    """
    normalised = rule_text.strip().lower()
    result = RULE_CLASSIFICATIONS.get(normalised)
    if result:
        return result

    # Fuzzy match: check if the normalised text is a substring
    for key, val in RULE_CLASSIFICATIONS.items():
        if key in normalised or normalised in key:
            return val

    # Default: send to LLM
    return ("llm", "eval_subjective")


def classify_rules(rules: list[str]) -> dict[str, list[str]]:
    """
    Classify a list of rules into buckets by type.

    Returns dict with keys "deterministic", "pattern", "llm",
    each mapping to a list of rule texts.
    """
    buckets: dict[str, list[str]] = {
        "deterministic": [],
        "pattern": [],
        "llm": [],
    }
    for rule in rules:
        rule_type, _ = classify_rule(rule)
        buckets[rule_type].append(rule)
    return buckets
