"""
scorer.py — Articulation scoring engine for ArticulateX Phase 1.

Takes the analysis dictionary from analyser.py and computes a
0–100 articulation score with transparent, rule-based deductions.
"""


MINIMUM_WORDS = 40
MINIMUM_DURATION = 12


def calculate_articulation_score(analysis: dict) -> dict:

    if analysis["word_count"] < MINIMUM_WORDS:
        return {
            "score": None,
            "valid": False,
            "rejection_reason": (
                f"Too short to score. You spoke "
                f"{analysis['word_count']} words. "
                f"Speak at least {MINIMUM_WORDS} words "
                f"(around 15 seconds) for a meaningful score."
            )
        }

    if analysis["duration_seconds"] < MINIMUM_DURATION:
        return {
            "score": None,
            "valid": False,
            "rejection_reason": (
                f"Speak for at least {MINIMUM_DURATION} seconds. "
                f"You spoke for "
                f"{round(analysis['duration_seconds'], 1)}s."
            )
        }

    score = 100.0

    # FILLER PENALTY — absolute, 4 points each, cap 40
    # 10+ fillers guarantees below 60
    filler_penalty = min(analysis["total_fillers"] * 4, 40)
    score -= filler_penalty

    # HESITATION PENALTY — separate, 3 points each, cap 15
    hesitation_penalty = min(
        analysis["hesitation_sounds"] * 3, 15
    )
    score -= hesitation_penalty

    # WPM PENALTY
    wpm = analysis["wpm"]
    if wpm > 180:
        score -= min((wpm - 180) * 0.3, 15)
    elif wpm < 100:
        score -= min((100 - wpm) * 0.3, 15)

    # NO CLEAR OPENING POSITION
    if not analysis["has_clear_opening_position"]:
        score -= 20

    # RAMBLING SENTENCES
    if analysis["avg_sentence_length"] > 25:
        score -= 10

    # OVERUSED WORDS — absolute, 4 points each, cap 16
    overuse_penalty = min(
        len(analysis["overused_words"]) * 4, 16
    )
    score -= overuse_penalty

    # REPETITION RATIO — extra penalty if severe
    word_count = max(analysis["word_count"], 1)
    repetition_ratio = (
        len(analysis["overused_words"]) / word_count
    )
    if repetition_ratio > 0.15:
        score -= 10

    return {
        "score": round(max(score, 0), 1),
        "valid": True,
        "rejection_reason": None
    }
