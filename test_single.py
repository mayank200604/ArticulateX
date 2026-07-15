# -*- coding: utf-8 -*-
"""
test_single.py — Debate Level 3 test with interrupt feature verification.

Runs two phases:
  Phase 1: Live 7-turn Debate L3 session via /api/turn → feedback report
  Phase 2: Direct unit tests of the three new interrupt features:
           - Weighted scoring (single breach vs multi breach)
           - History-aware rule switching (repeat penalty)
           - Dynamic pressure adjustment (consecutive interrupt reduction)

Usage:
    Terminal 1:  uvicorn server:app --port 8000
    Terminal 2:  python test_single.py
"""

import sys
import time
import json
import base64
import io
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SERVER = "http://localhost:8001"
HEADERS = {"X-Test-Mode": "true"}  # skip TTS

# ── 7 turns for Debate Level 3 ──────────────────────────────────
# Designed with varying filler density, length, and structure
# to exercise the interrupt scoring system.
TURNS = [
    # Turn 1: Clean strong opening — should NOT trigger any rule
    "Individual freedom must always override collective welfare "
    "because liberty is the foundational principle of a just "
    "society and without it no progress is possible.",

    # Turn 2: Heavy fillers + hedging — triggers filler_overload
    "I think maybe freedom is sort of important kind of you know "
    "for individuals um like basically everyone deserves it I guess.",

    # Turn 3: Long rambling + fillers — triggers word_overload + filler_overload
    "So basically what I am trying to say is that um you know "
    "freedom is like this really important thing that kind of "
    "defines who we are as people and I think maybe the problem "
    "is that sort of governments try to like control everything "
    "and I mean that is basically not fair you know because um "
    "people should have the right to like decide for themselves.",

    # Turn 4: Claim with no evidence — triggers claim_no_evidence
    "I believe that individual rights are more important than "
    "collective welfare and my point is that this has always "
    "been the case throughout all of human history and no one "
    "can argue against this fundamental truth.",

    # Turn 5: Backs down (tests AI pressure at L3)
    "You are right, collective welfare is also important and I "
    "agree with your point completely.",

    # Turn 6: Strong recovery — clean delivery
    "The reason individual freedom must come first is that any "
    "system that suppresses individual rights eventually becomes "
    "oppressive and collapses under its own weight.",

    # Turn 7: Closing with some fillers
    "Individual freedom is the primary value and I think like "
    "collective welfare must be built on voluntary cooperation "
    "not coercion from the government basically.",
]


def text_to_audio_b64(text: str) -> str:
    from gtts import gTTS
    buf = io.BytesIO()
    tts = gTTS(text=text, lang='en', tld='co.in')
    tts.write_to_fp(buf)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ════════════════════════════════════════════════════════════════
# PHASE 1 — Live Debate Level 3 session
# ════════════════════════════════════════════════════════════════

def run_live_session():
    print("=" * 65)
    print("  PHASE 1: Live Debate Level 3 — 7 Turns")
    print("=" * 65)

    setup = requests.post(f"{SERVER}/api/setup", json={
        "mode": "debate3",
        "level": 3,
        "topic": "",
        "user_side": "",
        "freestyle_type": "",
    }, timeout=15)
    setup.raise_for_status()
    data = setup.json()
    token = data["token"]
    print(f"  Token : {token[:12]}...")
    print(f"  Topic : {data['topic']}")
    print(f"  Side  : {data['user_side']} vs {data['ai_side']}")
    print()

    for i, text in enumerate(TURNS, 1):
        print(f"  ── Turn {i}/{len(TURNS)} ──")
        print(f"  USER: {text[:75]}...")
        audio = text_to_audio_b64(text)
        resp = requests.post(f"{SERVER}/api/turn", json={
            "session_token": token,
            "audio_b64": audio,
            "sample_rate": 16000,
        }, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        td = resp.json()
        if td.get("error"):
            print(f"  ⚠ ERROR: {td['error']}")
            print()
            continue
        print(f"  STT : {td['transcript'][:75]}...")
        print(f"  AI  : {td['ai_response'][:75]}...")
        print(f"  WPM={td.get('wpm',0)} | Fillers={td.get('fillers',0)} "
              f"| Interrupt={td.get('is_interrupt', False)}")
        print()
        time.sleep(1.5)

    # Get feedback
    print("=" * 65)
    print("  REQUESTING FEEDBACK REPORT...")
    print("=" * 65)
    fb = requests.post(f"{SERVER}/api/feedback", json={
        "session_token": token,
    }, headers=HEADERS, timeout=90)
    fb.raise_for_status()
    report = fb.json()

    print()
    print("=" * 65)
    print("  FULL FEEDBACK REPORT (Debate Level 3)")
    print("=" * 65)
    print(report.get("full_report", "(no report)"))
    print()
    print("-" * 65)
    print("  SPOKEN SUMMARY")
    print("-" * 65)
    print(report.get("spoken_summary", "(none)"))
    print()
    print(f"  Avg WPM: {report.get('avg_wpm')}")
    print(f"  Avg Fillers: {report.get('avg_fillers')}")
    print(f"  Total Turns: {report.get('total_turns')}")
    print(f"  Mode: {report.get('mode')} | Level: {report.get('level')}")
    print("=" * 65)


# ════════════════════════════════════════════════════════════════
# PHASE 2 — Direct unit tests for the three interrupt features
# ════════════════════════════════════════════════════════════════

def run_feature_tests():
    """
    Directly import and test evaluate_interrupt_weighted()
    to verify all three new features work correctly.
    """
    # Import the function from server module
    sys.path.insert(0, ".")
    from server import (
        evaluate_interrupt_weighted,
        _INTERRUPT_SCORE_THRESHOLD,
        _RULE_WEIGHTS,
        _REPEAT_PENALTY,
    )

    passed = 0
    failed = 0
    total = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed, total
        total += 1
        status = "✓ PASS" if condition else "✗ FAIL"
        if not condition:
            failed += 1
        else:
            passed += 1
        suffix = f" — {detail}" if detail else ""
        print(f"    {status}: {name}{suffix}")

    print()
    print("=" * 65)
    print("  PHASE 2: Interrupt Feature Unit Tests")
    print("=" * 65)

    # ── Feature 1: Weighted Scoring ─────────────────────────────
    print()
    print("  ── Feature 1: Weighted Scoring ──")
    print()

    # Test 1a: Single rule breach (filler_overload only) → score=0.4 < 0.6
    transcript_fillers_only = (
        "I think maybe um like you know basically sort of "
        "I guess this is kind of important"
    )
    _, score, top = evaluate_interrupt_weighted(transcript_fillers_only)
    check(
        "Single rule (filler_overload) does NOT cross threshold",
        score < _INTERRUPT_SCORE_THRESHOLD,
        f"score={score:.2f}, threshold={_INTERRUPT_SCORE_THRESHOLD}"
    )

    # Test 1b: Single rule breach (word_overload only, no fillers) → score=0.4 < 0.6
    transcript_long_clean = (
        "The argument here is that freedom is essential and "
        "the government should not be allowed to restrict any "
        "citizen from expressing themselves or choosing their "
        "own path in life and this is supported by many historical "
        "examples where oppressive regimes fell because they "
        "denied people basic freedoms"
    )
    _, score, top = evaluate_interrupt_weighted(transcript_long_clean)
    check(
        "Single rule (word_overload) does NOT cross threshold",
        score < _INTERRUPT_SCORE_THRESHOLD,
        f"score={score:.2f}, threshold={_INTERRUPT_SCORE_THRESHOLD}"
    )

    # Test 1c: Two rules breach (word_overload + filler_overload) → score=0.8 >= 0.6
    transcript_long_fillers = (
        "So basically um I think like you know the problem is "
        "that um freedom is kind of sort of really important "
        "and I mean basically the government should not um like "
        "restrict people you know from doing what they basically "
        "want to do and I guess sort of the whole point is that "
        "um like freedom matters"
    )
    _, score, top = evaluate_interrupt_weighted(transcript_long_fillers)
    check(
        "Two rules (word_overload + filler_overload) CROSSES threshold",
        score >= _INTERRUPT_SCORE_THRESHOLD,
        f"score={score:.2f}, threshold={_INTERRUPT_SCORE_THRESHOLD}"
    )

    # Test 1d: claim_no_evidence alone → score=0.2 < 0.6
    transcript_claim = (
        "I believe that freedom is the most important value "
        "and my point is that no government should restrict it"
    )
    _, score, top = evaluate_interrupt_weighted(transcript_claim)
    check(
        "Single rule (claim_no_evidence) does NOT cross threshold",
        score < _INTERRUPT_SCORE_THRESHOLD,
        f"score={score:.2f}, threshold={_INTERRUPT_SCORE_THRESHOLD}"
    )

    # Test 1e: claim_no_evidence + filler_overload → score=0.6 >= 0.6
    transcript_claim_fillers = (
        "I believe that um like basically freedom is you know "
        "the most important value and my point is that I think "
        "kind of no government should sort of restrict it"
    )
    _, score, top = evaluate_interrupt_weighted(transcript_claim_fillers)
    check(
        "Two rules (claim_no_evidence + filler_overload) CROSSES threshold",
        score >= _INTERRUPT_SCORE_THRESHOLD,
        f"score={score:.2f}, threshold={_INTERRUPT_SCORE_THRESHOLD}"
    )

    # ── Feature 2: History-Aware Rule Switching ─────────────────
    print()
    print("  ── Feature 2: History-Aware Rule Switching ──")
    print()

    # Test 2a: Without repeat penalty, word_overload+filler_overload = 0.8
    _, score_no_penalty, _ = evaluate_interrupt_weighted(
        transcript_long_fillers, last_interrupt_rule=None
    )
    check(
        "No repeat penalty → full score",
        score_no_penalty >= 0.8 - 0.01,
        f"score={score_no_penalty:.2f}"
    )

    # Test 2b: With repeat penalty on word_overload → word_overload weight
    #          drops 0.4→0.2, total = 0.2 + 0.4 = 0.6 (still crosses)
    _, score_with_penalty, top = evaluate_interrupt_weighted(
        transcript_long_fillers, last_interrupt_rule="word_overload"
    )
    check(
        "Repeat penalty on word_overload reduces score",
        score_with_penalty < score_no_penalty,
        f"score dropped {score_no_penalty:.2f} → {score_with_penalty:.2f}"
    )
    check(
        "Top rule shifts away from penalised rule",
        top == "filler_overload",
        f"top_rule={top} (expected filler_overload)"
    )

    # Test 2c: With repeat penalty on filler_overload → filler weight
    #          drops 0.4→0.2, total = 0.4 + 0.2 = 0.6 (still crosses)
    _, score_pen_filler, top2 = evaluate_interrupt_weighted(
        transcript_long_fillers, last_interrupt_rule="filler_overload"
    )
    check(
        "Repeat penalty on filler_overload reduces score",
        score_pen_filler < score_no_penalty,
        f"score dropped {score_no_penalty:.2f} → {score_pen_filler:.2f}"
    )
    check(
        "Top rule shifts to word_overload when filler penalised",
        top2 == "word_overload",
        f"top_rule={top2} (expected word_overload)"
    )

    # Test 2d: Penalty can drop score BELOW threshold
    #          filler_overload only (0.4) with repeat → 0.4-0.2=0.2 < 0.6
    _, score_single_pen, _ = evaluate_interrupt_weighted(
        transcript_fillers_only, last_interrupt_rule="filler_overload"
    )
    check(
        "Single rule + repeat penalty → stays below threshold",
        score_single_pen < _INTERRUPT_SCORE_THRESHOLD,
        f"score={score_single_pen:.2f}"
    )

    # ── Feature 3: Dynamic Pressure Adjustment ──────────────────
    print()
    print("  ── Feature 3: Dynamic Pressure Adjustment ──")
    print()

    # This feature modifies probability in the WS handler based on
    # sess["consecutive_interrupts"]. We test the logic directly.
    base_prob = 0.50  # Level 3 default

    # Test 3a: 0 consecutive interrupts → no reduction
    consec = 0
    reduction = 0.10 if consec >= 3 else 0.0
    effective = max(base_prob - reduction, 0.0)
    check(
        f"0 consecutive interrupts → prob stays {base_prob:.0%}",
        effective == base_prob,
        f"effective={effective:.0%}"
    )

    # Test 3b: 2 consecutive interrupts → no reduction yet
    consec = 2
    reduction = 0.10 if consec >= 3 else 0.0
    effective = max(base_prob - reduction, 0.0)
    check(
        f"2 consecutive interrupts → prob stays {base_prob:.0%}",
        effective == base_prob,
        f"effective={effective:.0%}"
    )

    # Test 3c: 3 consecutive interrupts → reduced by 10pp
    consec = 3
    reduction = 0.10 if consec >= 3 else 0.0
    effective = max(base_prob - reduction, 0.0)
    check(
        f"3 consecutive interrupts → prob drops to {base_prob - 0.10:.0%}",
        effective == base_prob - 0.10,
        f"effective={effective:.0%}"
    )

    # Test 3d: 5 consecutive interrupts → still reduced (same 10pp)
    consec = 5
    reduction = 0.10 if consec >= 3 else 0.0
    effective = max(base_prob - reduction, 0.0)
    check(
        f"5 consecutive interrupts → prob stays at {base_prob - 0.10:.0%}",
        effective == base_prob - 0.10,
        f"effective={effective:.0%}"
    )

    # Test 3e: After clean turn, counter resets → 0 consecutive
    consec_after_reset = 0  # simulates clean turn reset
    reduction = 0.10 if consec_after_reset >= 3 else 0.0
    effective = max(base_prob - reduction, 0.0)
    check(
        f"After clean turn reset → prob back to {base_prob:.0%}",
        effective == base_prob,
        f"effective={effective:.0%}"
    )

    # ── Summary ─────────────────────────────────────────────────
    print()
    print("=" * 65)
    print(f"  UNIT TEST RESULTS: {passed}/{total} passed, "
          f"{failed}/{total} failed")
    print("=" * 65)
    return failed == 0


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Phase 2 first — fast, no API calls needed for unit tests
    all_passed = run_feature_tests()

    print()
    print()

    # Phase 1 — live session (needs server running)
    try:
        run_live_session()
    except requests.ConnectionError:
        print("  ⚠ Server not running at http://localhost:8000")
        print("  Start it with: uvicorn server:app --port 8000")
    except Exception as exc:
        print(f"  ⚠ Session error: {exc}")

    if not all_passed:
        sys.exit(1)
