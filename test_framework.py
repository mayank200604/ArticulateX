# -*- coding: utf-8 -*-
"""
test_framework.py — ArticulateX Automated Testing Framework v2.0.

Production-ready evaluation with:
  • Three-tier rule evaluation (deterministic / pattern / LLM)
  • Multi-provider rate limit management
  • Evaluation caching
  • Pre-flight quota estimation
  • HTML / JSON / CSV reporting
  • Fast mode (3 scenarios) and Full mode (all scenarios)
  • Confidence scores in output

Usage:
    # Terminal 1 — start the server
    uvicorn server:app --host 0.0.0.0 --port 8000

    # Terminal 2 — run tests
    python test_framework.py                    # full mode
    python test_framework.py --mode fast        # quick test
    python test_framework.py --mode full        # complete test
    python test_framework.py --dry-run          # estimate only
    python test_framework.py --no-cache         # skip cache
"""

import os
import sys
import json
import time
import base64
import io
import argparse
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Fix Windows console encoding for Unicode symbols
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ── Evaluation framework imports ────────────────────────────────
from evaluation.config import (
    FAST_MODE, FULL_MODE, MAX_RULES_PER_BATCH,
    USE_CACHE, SKIP_TTS,
)
from evaluation.rule_classifier import classify_rule, classify_rules
from evaluation.deterministic_eval import evaluate_deterministic
from evaluation.pattern_eval import evaluate_pattern
from evaluation.llm_eval import evaluate_subjective_rules
from evaluation.provider_manager import ProviderManager
from evaluation.cache import EvalCache
from evaluation.api_tracker import APITracker
from evaluation.quota_guard import estimate_run
from evaluation.reporter import generate_reports


# ════════════════════════════════════════════════════════════════
# PART 1 — SIMULATED USER INPUTS (Text → Audio → Base64)
# ════════════════════════════════════════════════════════════════

def text_to_audio_b64(text: str) -> str:
    """
    Convert text to base64 audio bytes for API submission.
    Uses gTTS to synthesise speech, producing an MP3 which the
    server's ffmpeg-backed decoder can handle.
    """
    from gtts import gTTS

    buf = io.BytesIO()
    tts = gTTS(text=text, lang='en', tld='co.in')
    tts.write_to_fp(buf)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ════════════════════════════════════════════════════════════════
# PART 2 — SIMULATED TURN LISTS
# ════════════════════════════════════════════════════════════════

FREESTYLE_WORD_TURNS = [
    "Um so resilience is like you know the ability to kind of "
    "bounce back from difficult situations I think maybe.",

    "I have experienced resilience when I failed my exam and "
    "then I started again from the beginning.",

    "Thank you.",

    "Resilience is also about mental strength and not giving up "
    "even when things are hard for you.",

    "I think resilience kind of helps people in like professional "
    "life also you know.",

    "Yes I agree resilience is very important.",

    "Actually what I want to say is resilience makes you stronger "
    "after every failure.",

    "So this is what I feel about resilience and how it helps us "
    "in life.",
]

FREESTYLE_SCENARIO_TURNS = [
    "So basically I would just like say sorry and kind of explain "
    "what happened I think because I prepared for the wrong topic.",

    "I would try to stay calm and tell them that I made a mistake "
    "but I am ready to listen and contribute where I can.",

    "Thank you.",

    "I think the most important thing in that situation is to not "
    "panic and just be honest about the mistake you made.",

    "In my experience I have seen people handle situations like "
    "this by being transparent and asking for help from colleagues.",

    "The key is to show that even though you made a mistake you "
    "are still a professional and willing to learn from it.",

    "I would also prepare extra carefully for the next meeting so "
    "this never happens again and I can rebuild trust.",

    "So basically my lesson from this is that preparation matters "
    "but how you handle mistakes matters even more.",
]

DEBATE_L1_TURNS = [
    "Social media does more harm than good because it damages "
    "mental health and spreads misinformation among young people.",

    "I think maybe social media is kind of bad for young people "
    "you know because of the comparisons and anxiety.",

    "You are right, social media does have some benefits.",

    "The main problem is that algorithms are designed to keep "
    "people addicted and this causes harm.",

    "I mean I think the issue is also about how platforms earn "
    "money through engagement.",

    "So basically my point is that the business model of social "
    "media is the root cause of the harm.",

    "I agree with your point that regulation could help.",

    "In conclusion social media needs stronger regulation to "
    "reduce harm.",
]

DEBATE_L2_TURNS = [
    "AI creates more jobs than it destroys because new industries "
    "emerge with every technological revolution.",

    "Um like basically I think AI is good for jobs you know "
    "because of innovation and stuff.",

    "That is a valid point you make about job losses.",

    "The evidence from industrial revolution shows that technology "
    "always creates net positive employment.",

    "My main argument is that AI augments human capabilities "
    "rather than replacing them entirely and this leads to "
    "productivity gains.",

    "I think maybe I am not sure but the transition period might "
    "be difficult for some workers.",

    "Actually the real question is about retraining and whether "
    "governments will invest in that.",

    "So to summarize AI creates more jobs in the long run even "
    "if short term disruption exists.",
]

DEBATE_L3_TURNS = [
    "Individual freedom must always override collective welfare "
    "because liberty is the foundational principle of a just "
    "society.",

    "I think maybe freedom is sort of important kind of you know "
    "for individuals.",

    "Freedom is essential.",

    "You are right, collective welfare is also important and I "
    "agree with your point.",

    "The reason individual freedom must come first is that any "
    "system that suppresses individual rights eventually becomes "
    "oppressive.",

    "So my point was that freedom matters and I think you know "
    "individuals should be free basically.",

    "The Nordic model actually combines freedom with collective "
    "welfare effectively.",

    "Individual freedom is the primary value and collective "
    "welfare must be built on voluntary cooperation not coercion.",
]

WEIRD_TURNS = [
    "This man in the suit looks completely unbothered and "
    "confident like he owns the fountain.",

    "I think he is celebrating a promotion or some major personal "
    "victory.",

    "Maybe he made a bet with his colleagues and had to do this "
    "as a dare.",

    "The people around him are probably shocked but also secretly "
    "impressed by his confidence.",

    "I would be too embarrassed to do this myself but I admire "
    "his attitude completely.",

    "This reminds me that sometimes doing unexpected things "
    "brings more joy than following rules.",
]


# ════════════════════════════════════════════════════════════════
# PART 3 — RULES BY MODE (unchanged from v1)
# ════════════════════════════════════════════════════════════════

RULES_BY_MODE = {

    "freestyle": {
        "global": [
            "AI must ask exactly ONE follow-up question per turn",
            "AI must acknowledge what the user said briefly and genuinely",
            "AI must keep the user speaking comfortably",
            "AI response must be 1-2 sentences maximum",
            "AI must be warm and genuinely curious in tone",
            "AI must never challenge, correct, or evaluate content",
            "AI must never mention fillers or delivery issues during turns",
            "There is no right or wrong answer in freestyle",
            "No debate or argument in freestyle mode",
            "AI must never correct grammar or vocabulary",
            "AI must never correct Indian English expressions",
            "AI must never ask for data, statistics, evidence, or research",
            "AI must never challenge whether argument is factually correct",
            "AI must never judge intellectual strength of the point",
            "AI must never use banned phrases: great point / excellent / "
            "well argued / good point / well done / interesting / "
            "that said / however / perfectly said",
            "AI must respond in simple clear English",
            "AI must sound like a real person, not a robot",
            "AI must vary sentence starter every turn — never start "
            "two consecutive responses the same way",
        ],
        "feedback": [
            "Feedback harshness is 2 out of 10",
            "OVERALL VERDICT must be positive or neutral only",
            "WHAT WORKED must find at least 2 genuine things",
            "THREE THINGS TO FIX must be simple, kind, achievable",
            "THREE THINGS TO FIX must focus on fluency and flow only",
            "THREE THINGS TO FIX must never mention content quality "
            "or argument strength",
            "ONE EARNED ENCOURAGEMENT is mandatory",
            "Feedback must never evaluate factual accuracy of argument",
            "Feedback must never ask for strong evidence",
            "Feedback must never judge intellectual depth of point",
            "THREE THINGS TO FIX: minimum 2 out of 3 must be "
            "communication fixes",
            "THREE THINGS TO FIX must not contain invented statistics "
            "or research references",
        ]
    },

    "debate_level_1": {
        "global": [
            "Zero interruptions — interrupt probability is 0.0",
            "DEMAND_ONE_SENTENCE strategy is completely banned in Level 1",
            "PUSH_BACK_HARD strategy is completely banned in Level 1",
            "INTERRUPT_REDIRECT strategy is completely banned in Level 1",
            "CHANGE_TOPIC strategy is completely banned in Level 1",
            "MISUNDERSTAND strategy is completely banned in Level 1",
            "Turn 1-2 also bans DEVILS_ADVOCATE and ASK_FOR_EVIDENCE",
            "No demand for one sentence on Turn 1 regardless of level",
            "No ASK_TO_REPEAT on Turn 1 regardless of level",
            "No demand for one sentence when user spoke 30+ words",
            "No ASK_TO_REPEAT when user spoke 30+ words",
            "AI's job is to keep the user speaking — fluency is everything",
            "If user spoke fluently and finished thought: respond warmly "
            "and ask one simple follow-up",
            "If user trailed off: prompt to finish that thought",
            "If user used many fillers: note it once gently then move on — "
            "never block progress",
            "If user lost their thread: ask where they were going with that",
            "Never make the user feel wrong or stuck",
            "Never block the user from continuing",
            "Content check: only check if user is on topic",
            "Any on-topic point is acceptable — simple or complex, "
            "strong or weak",
            "Only call out content if completely off-topic",
            "Never ask user to be more specific about content in Level 1",
            "Tone: warm debate partner, firm but never harsh",
            "AI must never ask for data, statistics, evidence, or research",
            "AI must never challenge whether argument is factually correct",
            "AI must never judge intellectual strength of the point",
            "AI must never correct grammar or vocabulary",
            "AI must never correct Indian English expressions",
            "AI must never use banned phrases: great point / excellent / "
            "well argued / good point / well done / interesting / "
            "that said / however / perfectly said",
            "AI must respond in simple clear English",
            "AI must encourage user to use simple English",
            "Maximum 2-3 sentences per response",
            "Vary sentence starter every turn — never start two "
            "consecutive responses the same way",
            "Sound like a real person not a robot",
            "Anti-sycophancy: never validate just because user repeated "
            "point more confidently",
            "If user changed position without reasoning — call it out",
            "Never let a communication weakness pass because user "
            "seems frustrated or tired",
            "70/30 rule: 70% communication quality, 30% content relevance",
        ],
        "escalation": [
            "Turn 1-2: keep it very light",
            "Turn 3+: slightly more engaged but still gentle",
            "Difficulty increases gradually turn by turn",
            "Turn 8+: let user wrap up — ban DEVILS_ADVOCATE, "
            "ASK_FOR_EVIDENCE, SHARP_FOLLOWUP",
        ],
        "feedback": [
            "Feedback harshness: 3 out of 10",
            "Be honest but never crushing",
            "OVERALL VERDICT must acknowledge effort and identify "
            "one main thing to work on",
            "OVERALL VERDICT must never start with 'hesitant and unclear'",
            "WHAT WORKED must find at least 1-2 genuine communication "
            "positives — even small things count",
            "THREE THINGS TO FIX must be simple and achievable",
            "THREE THINGS TO FIX must all be communication-based — "
            "never about content strength",
            "ONE EARNED ENCOURAGEMENT is mandatory — must be specific "
            "and real",
            "Feedback must never say 'hesitant and unclear communicator'",
            "Feedback must never say 'struggles to convey'",
            "Feedback must never say 'lacks conviction'",
            "Feedback must never use language implying fundamental failure",
            "Feedback must never evaluate factual accuracy",
            "Feedback must never demand evidence or data",
            "THREE THINGS TO FIX: minimum 2 out of 3 must be "
            "communication fixes",
            "THREE THINGS TO FIX must not contain invented statistics "
            "or research references",
            "Each fix must follow four-part structure: "
            "POINT, REASON, EXAMPLE, TRY THIS INSTEAD",
        ]
    },

    "debate_level_2": {
        "global": [
            "Interrupt probability is 20-22% per turn",
            "Pause warning at 3 seconds",
            "AI picks topic in Level 2",
            "DEMAND_ONE_SENTENCE banned in first 2 turns for Level 2",
            "DEMAND_ONE_SENTENCE never repeats within 5 turns",
            "No demand for one sentence on Turn 1 regardless of level",
            "No ASK_TO_REPEAT on Turn 1 regardless of level",
            "No demand for one sentence when user spoke 30+ words",
            "Firmer than Level 1 — firm and direct from Turn 1",
            "No warmup and no encouragement mid-turn",
            "If unclear: challenge with 'I followed the words but not "
            "the point — say it more directly'",
            "If user agreed too quickly: 'You just changed your position "
            "— what do you actually believe?'",
            "If user lost thread: 'You started on X and ended on Y — "
            "which is your argument?'",
            "If user held position well: push back harder to test "
            "if they can maintain it",
            "If user repeated same point: 'You already said that — "
            "go deeper'",
            "Vary the challenge every single turn",
            "Vague on-topic points get precision challenge — "
            "'what specifically makes it so?' (not knowledge demand)",
            "Off-topic: redirect clearly and immediately",
            "Specific on-topic claim: accept it and challenge "
            "communication quality around it instead",
            "AI must never ask for data, statistics, evidence, or research",
            "AI must never challenge whether argument is factually correct",
            "AI must never judge intellectual strength of the point",
            "AI must never correct grammar or vocabulary",
            "AI must never correct Indian English expressions",
            "AI must never use banned phrases: great point / excellent / "
            "well argued / good point / well done / interesting",
            "AI must respond in simple clear English",
            "Maximum 2-3 sentences per response",
            "Vary sentence starter every turn",
            "Sound like a real person not a robot",
            "Anti-sycophancy: never validate just because user repeated "
            "point more confidently",
            "Position change without reasoning — call it out every time",
            "Never let communication weakness pass because user "
            "seems frustrated or tired",
            "70/30 rule: 70% communication quality, 30% content relevance",
            "Interrupt phrases must vary — never repeat same opener "
            "twice in a row",
        ],
        "feedback": [
            "Feedback harshness: 6 out of 10",
            "Honest and direct — no softening, no cruelty",
            "OVERALL VERDICT is honest assessment — not encouraging, "
            "not crushing, factual",
            "WHAT WORKED only if genuinely good — be selective",
            "THREE THINGS TO FIX more demanding than Level 1",
            "THREE THINGS TO FIX: at least one fix about structure "
            "or holding position",
            "ONE EARNED ENCOURAGEMENT only if deserved — skip if "
            "performance was average throughout",
            "Feedback must never evaluate factual accuracy",
            "Feedback must never demand evidence or data",
            "THREE THINGS TO FIX: minimum 2 out of 3 must be "
            "communication fixes",
            "Each fix must follow four-part structure: "
            "POINT, REASON, EXAMPLE, TRY THIS INSTEAD",
        ]
    },

    "debate_level_3": {
        "global": [
            "Interrupt probability is 50% per turn",
            "Pause terminates at 2 seconds — no warning",
            "AI picks topic in Level 3",
            "Side is randomly assigned (user_picks_side is False)",
            "CHANGE_TOPIC fires exactly on Turn 3 (guaranteed)",
            "DEMAND_ONE_SENTENCE never repeats within 3 turns in Level 3",
            "DEMAND_ONE_SENTENCE banned on Turn 1",
            "No demand for one sentence when user spoke 30+ words",
            "Say-it-again fires when total fillers exceed 5 "
            "(DEMAND_ONE_SENTENCE override)",
            "just_did_redo triggers when fillers > 5 at Level 3",
            "Immediate aggression from Turn 1 — no warmup",
            "Every turn has pressure — no exceptions",
            "Hedging challenged immediately: 'You said I think maybe — "
            "pick one. Do you believe this or not?'",
            "Backed down called out: 'You started on one side and just "
            "agreed with me — what happened to your argument?'",
            "Rambling called out: 'Too long. One point. Say it again.'",
            "Trailing off called out: 'You did not finish. Finish it.'",
            "Good clear delivery still gets pressure: 'Faster. Say it "
            "in half the words.'",
            "Strong position gets pushback: 'You said that — I "
            "completely disagree. Defend it.'",
            "Vague on-topic claim: precision challenge — 'what "
            "specifically is harmful? Be precise.'",
            "Point drifted across turns: 'Your point in Turn 2 and "
            "your point now are different things — which is your "
            "actual argument?'",
            "Off-topic: called out sharply and immediately",
            "Specific clear claim: force user to HOLD it and DEFEND it "
            "under maximum pressure",
            "Tone: relentless, aggressive but not rude",
            "AI must never ask for data, statistics, evidence, or research",
            "AI must never challenge whether argument is factually correct",
            "AI must never judge intellectual strength of the point",
            "AI must never correct grammar or vocabulary",
            "AI must never correct Indian English expressions",
            "AI must never use banned phrases: great point / excellent / "
            "well argued / good point / well done / interesting",
            "AI must respond in simple clear English",
            "Maximum 2-3 sentences per response",
            "Vary sentence starter every turn",
            "Sound like a real person not a robot",
            "Anti-sycophancy at maximum: never validate just because "
            "user repeated point more confidently",
            "Position change without reasoning — call it out every time "
            "not just once",
            "Never let communication weakness pass because user "
            "seems frustrated or tired",
            "If delivery flaw existed — flaw still exists even if user "
            "sounds more confident now",
            "70/30 rule: 70% communication quality, 30% content relevance",
            "Interrupt phrases must vary — never repeat same opener "
            "twice in a row",
        ],
        "feedback": [
            "Feedback harshness: 10 out of 10 — zero softening",
            "Treat user like a professional under evaluation",
            "OVERALL VERDICT reflects Level 3 standards — mediocre "
            "performance is called mediocre directly",
            "OVERALL VERDICT must never soften with 'showed potential'",
            "WHAT WORKED: only if genuinely strong — if nothing was "
            "genuinely strong write 'Nothing in this session stood "
            "out at Level 3 standards'",
            "THREE THINGS TO FIX must be demanding and specific",
            "THREE THINGS TO FIX must quote exact turn numbers and "
            "exact words",
            "THREE THINGS TO FIX: at least one fix about confidence "
            "under pressure",
            "ONE EARNED ENCOURAGEMENT only if performance was "
            "objectively strong — if not skip entirely and write "
            "'No standout moment this session'",
            "Feedback must never say 'showed potential'",
            "Feedback must never say 'willingness to engage'",
            "Feedback must never say 'good attempt'",
            "Feedback must never use any verdict that could apply "
            "to Level 1",
            "Feedback must never evaluate factual accuracy",
            "Feedback must never demand evidence or data",
            "THREE THINGS TO FIX: minimum 2 out of 3 must be "
            "communication fixes",
            "Each fix must follow four-part structure: "
            "POINT, REASON, EXAMPLE, TRY THIS INSTEAD",
        ]
    },

    "weird_situation": {
        "global": [
            "AI must ask ONE specific follow-up question about something "
            "the user mentioned",
            "Follow-up must connect to what user actually said — "
            "not a generic question",
            "AI must react curiously and playfully to what user said",
            "Conversation should feel like two people exploring "
            "something strange together",
            "AI must never evaluate content quality",
            "AI must never challenge the user's interpretation",
            "Goal is spontaneous speech — anything goes",
            "No correct answer — no topic to stay on",
            "AI response must be 1-2 sentences",
            "Tone must be curious and playful",
            "AI must never correct grammar or vocabulary",
            "AI must never correct Indian English expressions",
            "AI must never ask for data, statistics, evidence, or research",
            "AI must never use banned phrases: great point / excellent / "
            "well argued / good point / well done / interesting",
            "AI must respond in simple clear English",
            "AI must vary sentence starter every turn",
            "AI must sound like a real person not a robot",
        ],
        "feedback": [
            "Feedback harshness is 2 out of 10",
            "OVERALL VERDICT must be positive or neutral only",
            "WHAT WORKED must find at least 2 genuine things",
            "THREE THINGS TO FIX must be simple, kind, achievable",
            "THREE THINGS TO FIX must focus on fluency and flow only",
            "THREE THINGS TO FIX must never mention content quality "
            "or argument strength",
            "ONE EARNED ENCOURAGEMENT is mandatory",
            "Feedback must never evaluate factual accuracy",
            "THREE THINGS TO FIX: minimum 2 out of 3 must be "
            "communication fixes",
        ]
    }
}


# ════════════════════════════════════════════════════════════════
# PART 4 — THREE-TIER RULE EVALUATOR
# ════════════════════════════════════════════════════════════════

def evaluate_rules_three_tier(
    rules: list,
    turns: list,
    mode: str,
    level: int,
    category: str,
    feedback_text: str = "",
    provider_manager: ProviderManager = None,
    cache: EvalCache = None,
    scenario_name: str = "",
) -> list:
    """
    Evaluate rules using three-tier strategy:
    1. Deterministic rules → code only
    2. Pattern rules → regex/NLP
    3. Subjective rules → LLM-as-judge (batched, cached)

    Global / escalation / feedback stay as SEPARATE batches.
    No merging across categories.
    """
    if not rules:
        return []

    # Classify rules
    buckets = classify_rules(rules)
    all_results = []

    # ── Tier 1: Deterministic ────────────────────────────────────
    det_rules = buckets["deterministic"]
    if det_rules:
        for rule in det_rules:
            _, evaluator_name = classify_rule(rule)
            results = evaluate_deterministic(
                rule=rule,
                evaluator_name=evaluator_name,
                turns=turns,
                feedback_text=feedback_text,
            )
            for r in results:
                r["category"] = category
            all_results.extend(results)

    # ── Tier 2: Pattern ──────────────────────────────────────────
    pat_rules = buckets["pattern"]
    if pat_rules:
        for rule in pat_rules:
            _, evaluator_name = classify_rule(rule)
            results = evaluate_pattern(
                rule=rule,
                evaluator_name=evaluator_name,
                turns=turns,
                feedback_text=feedback_text,
            )
            for r in results:
                r["category"] = category
            all_results.extend(results)

    # ── Tier 3: LLM (subjective) ────────────────────────────────
    llm_rules = buckets["llm"]
    if llm_rules:
        results = evaluate_subjective_rules(
            rules=llm_rules,
            turns=turns,
            mode=mode,
            level=level,
            category=category,
            feedback_text=feedback_text,
            provider_manager=provider_manager,
            cache=cache,
            scenario=scenario_name,
        )
        for r in results:
            r["category"] = category
        all_results.extend(results)

    return all_results


# ════════════════════════════════════════════════════════════════
# PART 5 — SESSION RUNNER
# ════════════════════════════════════════════════════════════════

def run_test_session(
    mode: str,
    level: int,
    turns: list,
    topic: str = "",
    user_side: str = "",
    freestyle_type: str = "",
    server_url: str = "http://localhost:8000",
    max_turns: int = None,
) -> dict:
    """
    Runs a complete test session and returns
    all responses and metadata.
    """
    # Truncate turns if max_turns is set (fast mode)
    if max_turns and len(turns) > max_turns:
        turns = turns[:max_turns]

    # Setup session
    setup_payload = {
        "mode": mode,
        "level": level,
        "topic": topic,
        "user_side": user_side,
        "freestyle_type": freestyle_type,
    }

    headers = {}
    if SKIP_TTS:
        headers["X-Test-Mode"] = "true"

    print(f"  Setting up session: mode={mode}, level={level}")
    setup_resp = requests.post(
        f"{server_url}/api/setup",
        json=setup_payload,
        timeout=15,
    )
    setup_resp.raise_for_status()
    session_data = setup_resp.json()
    token = session_data["token"]
    topic_assigned = session_data.get("topic", topic)
    user_side_assigned = session_data.get("user_side", user_side)
    ai_side = session_data.get("ai_side", "")

    print(f"  Token: {token[:8]}...")
    print(f"  Topic: {topic_assigned}")
    if user_side_assigned:
        print(f"  User side: {user_side_assigned} | AI side: {ai_side}")

    results = []

    for i, user_text in enumerate(turns, 1):
        print(f"\n  ── Turn {i}/{len(turns)} ──")
        print(f"  USER: {user_text[:70]}...")

        # Convert text to audio
        try:
            audio_b64 = text_to_audio_b64(user_text)
        except Exception as exc:
            print(f"  ✗ TTS failed: {exc}")
            results.append({
                "turn": i,
                "user_input": user_text,
                "transcript": "",
                "ai_response": "",
                "is_interrupt": False,
                "wpm": 0,
                "fillers": 0,
                "just_did_redo": False,
                "error": f"TTS failed: {exc}",
            })
            continue

        # Submit turn
        try:
            turn_resp = requests.post(
                f"{server_url}/api/turn",
                json={
                    "session_token": token,
                    "audio_b64": audio_b64,
                    "sample_rate": 16000,
                },
                headers=headers,
                timeout=60,
            )
            turn_resp.raise_for_status()
            turn_data = turn_resp.json()
        except Exception as exc:
            print(f"  ✗ Turn API failed: {exc}")
            results.append({
                "turn": i,
                "user_input": user_text,
                "transcript": "",
                "ai_response": "",
                "is_interrupt": False,
                "wpm": 0,
                "fillers": 0,
                "just_did_redo": False,
                "error": f"Turn API failed: {exc}",
            })
            continue

        # Handle error responses from the server
        if turn_data.get("error"):
            print(f"  ⚠ Server error: {turn_data['error']}")
            results.append({
                "turn": i,
                "user_input": user_text,
                "transcript": "",
                "ai_response": "",
                "is_interrupt": False,
                "wpm": 0,
                "fillers": 0,
                "just_did_redo": False,
                "error": turn_data["error"],
            })
            time.sleep(0.5)
            continue

        transcript = turn_data.get("transcript", "")
        ai_response = turn_data.get("ai_response", "")

        print(f"  STT:  {transcript[:70]}...")
        print(f"  AI:   {ai_response[:70]}...")
        print(f"  WPM: {turn_data.get('wpm', 0)} | "
              f"Fillers: {turn_data.get('fillers', 0)} | "
              f"Interrupt: {turn_data.get('is_interrupt', False)}")

        results.append({
            "turn": i,
            "user_input": user_text,
            "transcript": transcript,
            "ai_response": ai_response,
            "is_interrupt": turn_data.get("is_interrupt", False),
            "wpm": turn_data.get("wpm", 0),
            "fillers": turn_data.get("fillers", 0),
            "just_did_redo": turn_data.get("just_did_redo", False),
            "error": None,
        })

        # Small delay between turns to avoid rate limiting
        time.sleep(1.5)

    # Get feedback
    print(f"\n  ── Requesting feedback ──")
    feedback_data = {}
    try:
        feedback_resp = requests.post(
            f"{server_url}/api/feedback",
            json={"session_token": token},
            headers=headers,
            timeout=60,
        )
        feedback_resp.raise_for_status()
        feedback_data = feedback_resp.json()
        report = feedback_data.get("full_report", "")
        if report:
            print(f"  Feedback received: {len(report)} chars")
        else:
            print(f"  ⚠ No feedback report generated")
    except Exception as exc:
        print(f"  ✗ Feedback API failed: {exc}")
        feedback_data = {"error": str(exc)}

    return {
        "mode": mode,
        "level": level,
        "topic": topic_assigned,
        "user_side": user_side_assigned,
        "ai_side": ai_side,
        "turns": results,
        "feedback": feedback_data,
    }


# ════════════════════════════════════════════════════════════════
# PART 6 — FULL TEST RUNNER
# ════════════════════════════════════════════════════════════════

def run_all_tests(
    server_url: str = "http://localhost:8000",
    mode_preset: str = "full",
    use_cache: bool = True,
    dry_run: bool = False,
):
    """
    Main entry point. Runs scenarios, evaluates rules with
    three-tier strategy, produces multi-format reports.
    """
    print("\n" + "=" * 60)
    print("  ARTICULATEX — AUTOMATED TEST FRAMEWORK v2.0")
    print("=" * 60 + "\n")

    # ── Initialize evaluation infrastructure ─────────────────────
    tracker = APITracker()
    provider_mgr = ProviderManager(tracker=tracker)
    cache = EvalCache() if use_cache else None

    # ── Define all test scenarios ────────────────────────────────
    all_scenarios = [
        {
            "name": "FreeStyle — Random Word",
            "mode": "freestyle",
            "level": 0,
            "rules_key": "freestyle",
            "turns": FREESTYLE_WORD_TURNS,
            "topic": "resilience",
            "user_side": "",
            "freestyle_type": "word",
        },
        {
            "name": "FreeStyle — Scenario",
            "mode": "freestyle",
            "level": 0,
            "rules_key": "freestyle",
            "turns": FREESTYLE_SCENARIO_TURNS,
            "topic": "You just walked into a meeting and realised "
                     "you prepared for the wrong topic. You have "
                     "30 seconds before it starts.",
            "user_side": "",
            "freestyle_type": "scenario",
        },
        {
            "name": "Debate Level 1",
            "mode": "debate1",
            "level": 1,
            "rules_key": "debate_level_1",
            "turns": DEBATE_L1_TURNS,
            "topic": "Social media does more harm than good",
            "user_side": "for",
            "freestyle_type": "",
        },
        {
            "name": "Debate Level 2",
            "mode": "debate2",
            "level": 2,
            "rules_key": "debate_level_2",
            "turns": DEBATE_L2_TURNS,
            "topic": "Artificial intelligence will create more "
                     "jobs than it destroys",
            "user_side": "for",
            "freestyle_type": "",
        },
        {
            "name": "Debate Level 3",
            "mode": "debate3",
            "level": 3,
            "rules_key": "debate_level_3",
            "turns": DEBATE_L3_TURNS,
            "topic": "Individual freedom must always override "
                     "collective welfare",
            "user_side": "for",
            "freestyle_type": "",
        },
        {
            "name": "Weird Situation",
            "mode": "weird",
            "level": 0,
            "rules_key": "weird_situation",
            "turns": WEIRD_TURNS,
            "topic": "A man in a full business suit swimming in "
                     "a public fountain",
            "user_side": "",
            "freestyle_type": "",
        },
    ]

    # ── Apply mode preset ────────────────────────────────────────
    preset = FULL_MODE if mode_preset == "full" else FAST_MODE
    max_turns = preset.get("max_turns")

    if preset.get("scenario_selection"):
        selected_names = set(preset["scenario_selection"])
        scenarios = [
            s for s in all_scenarios
            if s["name"] in selected_names
        ]
    else:
        scenarios = all_scenarios

    if preset.get("max_scenarios") and len(scenarios) > preset["max_scenarios"]:
        scenarios = scenarios[:preset["max_scenarios"]]

    print(f"  Mode: {preset['name'].upper()}")
    print(f"  Scenarios: {len(scenarios)}")
    if max_turns:
        print(f"  Max turns per scenario: {max_turns}")
    print()

    # ── Pre-flight quota estimation ──────────────────────────────
    # Temporarily apply max_turns to scenario copies for estimation
    est_scenarios = []
    for s in scenarios:
        s_copy = dict(s)
        if max_turns:
            s_copy["turns"] = s_copy["turns"][:max_turns]
        est_scenarios.append(s_copy)

    estimate = estimate_run(est_scenarios, RULES_BY_MODE)
    estimate.print_report()

    if dry_run:
        print("  ── DRY RUN — not executing. ──\n")
        return []

    if not estimate.can_proceed:
        print("  ✗ Cannot proceed — check warnings above.")
        return []

    # ── Run scenarios ────────────────────────────────────────────
    all_results = []

    for sc_idx, scenario in enumerate(scenarios, 1):
        print(f"\n{'━' * 60}")
        print(f"  [{sc_idx}/{len(scenarios)}] TESTING: {scenario['name']}")
        print(f"{'━' * 60}")

        # Run the session
        session_result = run_test_session(
            mode=scenario["mode"],
            level=scenario["level"],
            turns=scenario["turns"],
            topic=scenario.get("topic", ""),
            user_side=scenario.get("user_side", ""),
            freestyle_type=scenario.get("freestyle_type", ""),
            server_url=server_url,
            max_turns=max_turns,
        )

        # ── Evaluate rules with three-tier strategy ──────────────
        rules = RULES_BY_MODE.get(scenario["rules_key"], {})
        scenario_results = {
            "scenario": scenario["name"],
            "mode": scenario["mode"],
            "level": scenario["level"],
            "topic": session_result["topic"],
            "rule_evaluations": [],
            "turn_data": session_result["turns"],
            "feedback_received": session_result["feedback"],
        }

        # Filter to turns that actually got AI responses
        valid_turns = [
            t for t in session_result["turns"]
            if t["ai_response"] and not t.get("error")
        ]

        if not valid_turns:
            print("  ⚠ No valid turns with AI responses — skipping evaluation")
            all_results.append(scenario_results)
            continue

        # ── Evaluate GLOBAL rules (separate batch) ───────────────
        global_rules = rules.get("global", [])
        if global_rules:
            buckets = classify_rules(global_rules)
            n_det = len(buckets["deterministic"])
            n_pat = len(buckets["pattern"])
            n_llm = len(buckets["llm"])
            print(f"\n  ── Evaluating {len(global_rules)} global rules ──")
            print(f"     Deterministic: {n_det} | Pattern: {n_pat} | LLM: {n_llm}")

            eval_results = evaluate_rules_three_tier(
                rules=global_rules,
                turns=valid_turns[:6],
                mode=scenario["mode"],
                level=scenario["level"],
                category="global",
                provider_manager=provider_mgr,
                cache=cache,
                scenario_name=scenario["name"],
            )
            for ev in eval_results:
                scenario_results["rule_evaluations"].append(ev)
                _print_eval_result(ev)

            # Rate limit protection between categories
            time.sleep(1.0)

        # ── Evaluate ESCALATION rules (separate batch) ───────────
        escalation_rules = rules.get("escalation", [])
        if escalation_rules and len(valid_turns) >= 4:
            buckets = classify_rules(escalation_rules)
            n_det = len(buckets["deterministic"])
            n_pat = len(buckets["pattern"])
            n_llm = len(buckets["llm"])
            print(f"\n  ── Evaluating {len(escalation_rules)} escalation rules ──")
            print(f"     Deterministic: {n_det} | Pattern: {n_pat} | LLM: {n_llm}")

            eval_results = evaluate_rules_three_tier(
                rules=escalation_rules,
                turns=valid_turns,
                mode=scenario["mode"],
                level=scenario["level"],
                category="escalation",
                provider_manager=provider_mgr,
                cache=cache,
                scenario_name=scenario["name"],
            )
            for ev in eval_results:
                scenario_results["rule_evaluations"].append(ev)
                _print_eval_result(ev)

            time.sleep(1.0)

        # ── Evaluate FEEDBACK rules (separate batch) ─────────────
        feedback_text = session_result["feedback"].get("full_report", "")
        feedback_rules = rules.get("feedback", [])
        if feedback_text and feedback_rules:
            buckets = classify_rules(feedback_rules)
            n_det = len(buckets["deterministic"])
            n_pat = len(buckets["pattern"])
            n_llm = len(buckets["llm"])
            print(f"\n  ── Evaluating {len(feedback_rules)} feedback rules ──")
            print(f"     Deterministic: {n_det} | Pattern: {n_pat} | LLM: {n_llm}")

            eval_results = evaluate_rules_three_tier(
                rules=feedback_rules,
                turns=[],
                mode=scenario["mode"],
                level=scenario["level"],
                category="feedback",
                feedback_text=feedback_text,
                provider_manager=provider_mgr,
                cache=cache,
                scenario_name=scenario["name"],
            )
            for ev in eval_results:
                scenario_results["rule_evaluations"].append(ev)
                _print_eval_result(ev)

            time.sleep(1.0)
        elif not feedback_text and feedback_rules:
            print(f"\n  ⚠ No feedback text — skipping feedback rules")

        all_results.append(scenario_results)

        # Inter-scenario delay for rate limit recovery
        if sc_idx < len(scenarios):
            print(f"\n  ⏳ Inter-scenario cooldown (3s)...")
            time.sleep(3.0)

    # ════════════════════════════════════════════════════════════
    # Print summary
    # ════════════════════════════════════════════════════════════
    _print_summary(all_results)

    # ════════════════════════════════════════════════════════════
    # Save cache
    # ════════════════════════════════════════════════════════════
    if cache:
        cache.save_to_disk()
        print(f"  Cache: {cache.stats()}")

    # ════════════════════════════════════════════════════════════
    # Generate reports
    # ════════════════════════════════════════════════════════════
    print(f"\n  Generating reports...")
    report_paths = generate_reports(
        all_results=all_results,
        api_data=tracker.to_dict(),
        cache_stats=cache.stats() if cache else {},
        quota_estimate=estimate.summary(),
        mode_name=mode_preset,
    )

    print(f"\n  Reports generated:")
    for fmt, path in report_paths.items():
        print(f"    {fmt.upper()}: {path}")

    # Print provider status
    print(f"\n  Provider status:")
    for name, status in provider_mgr.status().items():
        if status["enabled"]:
            print(f"    {name}: {status['daily_requests']} requests, "
                  f"{'available' if status['available'] else 'COOLDOWN'}")

    print()
    return all_results


def _print_eval_result(ev: dict):
    """Print a single evaluation result with icon."""
    result = ev.get("result", "?")
    confidence = ev.get("confidence", 0.0)
    eval_type = ev.get("eval_type", "?")

    icon = {
        "PASS": "✓", "FAIL": "✗", "PARTIAL": "~",
        "SKIP": "⊘", "ERROR": "⚠", "UNKNOWN": "?"
    }.get(result, "?")

    type_tag = {
        "deterministic": "DET",
        "pattern": "PAT",
        "llm": "LLM",
    }.get(eval_type, "???")

    conf_str = f" [{confidence:.0%}]" if confidence < 1.0 else ""

    print(f"  {icon} [{type_tag}] {ev['rule'][:55]}{conf_str}")
    if result not in ("PASS", "SKIP"):
        print(f"    → {ev.get('reason', '')[:80]}")


def _print_summary(all_results: list):
    """Print the test summary."""
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)

    total_rules = 0
    total_pass = 0
    total_partial = 0
    total_fail = 0
    total_skip = 0
    total_error = 0

    det_count = pat_count = llm_count = 0

    for scenario_result in all_results:
        evals = scenario_result["rule_evaluations"]
        passes = sum(1 for e in evals if e["result"] == "PASS")
        partials = sum(1 for e in evals if e["result"] == "PARTIAL")
        fails = sum(1 for e in evals if e["result"] == "FAIL")
        skips = sum(1 for e in evals if e["result"] == "SKIP")
        errors = sum(1 for e in evals if e["result"] in ("ERROR", "UNKNOWN"))
        total = len(evals)

        total_rules += total
        total_pass += passes
        total_partial += partials
        total_fail += fails
        total_skip += skips
        total_error += errors

        # Count by eval type
        for e in evals:
            t = e.get("eval_type", "")
            if t == "deterministic":
                det_count += 1
            elif t == "pattern":
                pat_count += 1
            elif t == "llm":
                llm_count += 1

        evaluated = total - skips
        pct = round((passes / evaluated) * 100) if evaluated > 0 else 0
        print(f"\n  {scenario_result['scenario']}")
        print(f"  {'─' * 40}")
        print(f"  PASS: {passes}/{evaluated} ({pct}%)")
        if partials > 0:
            print(f"  PARTIAL: {partials}")
        if fails > 0:
            print(f"  FAIL: {fails}")
            for e in evals:
                if e["result"] == "FAIL":
                    print(f"    ✗ {e['rule'][:55]}")
                    print(f"      {e.get('reason', '')[:80]}")
        if skips > 0:
            print(f"  SKIP: {skips}")
        if errors > 0:
            print(f"  ERROR: {errors}")

    evaluated_total = total_rules - total_skip
    overall_pct = round(
        (total_pass / evaluated_total) * 100
    ) if evaluated_total > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"  OVERALL: {total_pass}/{evaluated_total} rules "
          f"passing ({overall_pct}%)")
    if total_partial > 0:
        print(f"  PARTIAL: {total_partial}")
    if total_fail > 0:
        print(f"  FAILING: {total_fail}")
    if total_skip > 0:
        print(f"  SKIPPED: {total_skip}")
    if total_error > 0:
        print(f"  ERRORS:  {total_error}")

    print(f"\n  Evaluation breakdown:")
    print(f"    Deterministic (code): {det_count} rules")
    print(f"    Pattern (regex/NLP):  {pat_count} rules")
    print(f"    LLM (subjective):     {llm_count} rules")
    print(f"{'=' * 60}\n")


# ════════════════════════════════════════════════════════════════
# PART 7 — CLI & MAIN EXECUTION
# ════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="ArticulateX Automated Test Framework v2.0"
    )
    parser.add_argument(
        "--mode", choices=["fast", "full"], default="full",
        help="Test mode: fast (3 scenarios, 5 turns) or full (all)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Estimate API usage without running tests"
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Disable evaluation caching"
    )
    parser.add_argument(
        "--server", default=None,
        help="Server URL (default: http://localhost:8000)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    SERVER_URL = args.server or os.getenv(
        "ARTICULATEX_SERVER_URL", "http://localhost:8000"
    )

    print("\n" + "─" * 60)
    print("  ArticulateX — Automated Test Framework v2.0")
    print("─" * 60)
    print(f"  Server: {SERVER_URL}")
    print(f"  Mode:   {args.mode.upper()}")
    print(f"  Cache:  {'ON' if not args.no_cache else 'OFF'}")
    print(f"  Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 60)

    if args.dry_run:
        print("\n  ── DRY RUN MODE ──")

    # Pre-flight checks
    print("\n  Checking dependencies...")

    # Check gTTS
    try:
        from gtts import gTTS
        print("  ✓ gTTS available")
    except ImportError:
        print("  ✗ gTTS not installed. Run: pip install gtts")
        sys.exit(1)

    # Check Groq
    try:
        from groq import Groq
        print("  ✓ Groq SDK available")
    except ImportError:
        print("  ✗ Groq SDK not installed. Run: pip install groq")
        sys.exit(1)

    # Check API keys
    if not os.getenv("GROQ_API_KEY"):
        print("  ⚠ GROQ_API_KEY not set — Groq provider disabled")
    else:
        print("  ✓ GROQ_API_KEY found")

    if not os.getenv("GEMINI_API_KEY"):
        print("  ⚠ GEMINI_API_KEY not set — Gemini provider disabled")
    else:
        print("  ✓ GEMINI_API_KEY found")

    if os.getenv("OPENAI_API_KEY"):
        print("  ✓ OPENAI_API_KEY found (optional)")
    if os.getenv("ANTHROPIC_API_KEY"):
        print("  ✓ ANTHROPIC_API_KEY found (optional)")

    # Quick connectivity check (skip for dry run)
    if not args.dry_run:
        print(f"\n  Connecting to server at {SERVER_URL}...")
        try:
            resp = requests.get(SERVER_URL, timeout=5)
            print(f"  ✓ Server is running (status {resp.status_code})\n")
        except requests.ConnectionError:
            print("  ✗ Server not reachable. Start it first:")
            print("    uvicorn server:app --host 0.0.0.0 --port 8000")
            sys.exit(1)
        except Exception as exc:
            print(f"  ✗ Connection error: {exc}")
            sys.exit(1)

        print("  Starting tests in 3 seconds...")
        time.sleep(3)

    run_all_tests(
        server_url=SERVER_URL,
        mode_preset=args.mode,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )
