"""
weakness_detector.py — Personalized weakness detection for ArticulateX.

Applies rule-based analysis to the user profile from get_user_profile()
and returns a list of active weakness flags with severity scores (1-3).

No LLM calls. HEDGING_HABIT is computed from stored transcripts since
the sessions table does not have a confidence_count column.
"""

from core.db import get_conn
from core.memory import _use_conn
from engine.confidence import analyse_confidence


def detect_weaknesses(profile: dict, *, conn=None) -> list[dict]:
    """
    Detect active communication weaknesses from user profile.

    Parameters
    ----------
    profile : dict
        Output from get_user_profile(). Must contain keys:
        last_5_sessions, avg_wpm, avg_fillers, total_sessions
    conn : connection, optional
        An existing DB connection to reuse for hedging transcript lookup.

    Returns
    -------
    list of dicts, each with keys: flag, severity (1-3), detail
    """
    weaknesses = []
    sessions = profile.get("last_5_sessions", [])

    if not sessions or profile.get("total_sessions", 0) == 0:
        return weaknesses

    avg_fillers = profile.get("avg_fillers", 0)
    avg_wpm = profile.get("avg_wpm", 0)

    # ── FILLER_HABIT: avg fillers across last 5 > 6 ─────────────
    if avg_fillers > 6:
        if avg_fillers > 15:
            severity = 3
        elif avg_fillers > 10:
            severity = 2
        else:
            severity = 1
        weaknesses.append({
            "flag": "FILLER_HABIT",
            "severity": severity,
            "detail": f"avg {avg_fillers} fillers/session",
        })

    # ── PACE_ISSUE: avg WPM consistently > 160 or < 90 ──────────
    if avg_wpm > 0:
        if avg_wpm > 190 or avg_wpm < 70:
            severity = 3
            direction = "too fast" if avg_wpm > 160 else "too slow"
        elif avg_wpm > 175 or avg_wpm < 80:
            severity = 2
            direction = "too fast" if avg_wpm > 160 else "too slow"
        elif avg_wpm > 160 or avg_wpm < 90:
            severity = 1
            direction = "too fast" if avg_wpm > 160 else "too slow"
        else:
            severity = 0
            direction = ""

        if severity > 0:
            weaknesses.append({
                "flag": "PACE_ISSUE",
                "severity": severity,
                "detail": f"avg WPM {avg_wpm} — {direction}",
            })

    # ── HEDGING_HABIT: compute from transcripts (last 5 only) ────
    hedging_avg = _compute_hedging_from_transcripts(sessions, conn=conn)
    if hedging_avg > 5:
        if hedging_avg > 12:
            severity = 3
        elif hedging_avg > 8:
            severity = 2
        else:
            severity = 1
        weaknesses.append({
            "flag": "HEDGING_HABIT",
            "severity": severity,
            "detail": f"avg {hedging_avg:.1f} hedging signals/session",
        })

    # ── STUCK_* flags: based on profile-level trend labels ─────────
    # Trend labels track raw metric direction:
    #   "declining" = value going down, "improving" = value going up.
    # For WPM  : declining/flat = bad  → fire STUCK_WPM
    # For fillers: declining = good (fewer fillers), flat = bad → fire STUCK_FILLERS
    wpm_trend = profile.get("wpm_trend", "flat")
    filler_trend = profile.get("filler_trend", "flat")

    if wpm_trend in ("flat", "declining") and len(sessions) >= 3:
        last_3_wpm = [s["avg_wpm"] for s in sessions[-3:] if s["avg_wpm"] > 0]
        severity = 2 if wpm_trend == "declining" else 1
        weaknesses.append({
            "flag": "STUCK_WPM",
            "severity": severity,
            "detail": f"WPM trend is {wpm_trend} "
                      f"(last 3: {', '.join(str(v) for v in last_3_wpm)})",
        })

    if filler_trend == "flat" and len(sessions) >= 3:
        last_3_fil = [s["avg_fillers"] for s in sessions[-3:]]
        weaknesses.append({
            "flag": "STUCK_FILLERS",
            "severity": 1,
            "detail": f"filler count not improving "
                      f"(last 3: {', '.join(str(v) for v in last_3_fil)})",
        })

    return weaknesses


def format_weakness_summary(weaknesses: list[dict]) -> str:
    """
    Convert weakness flags into a compact natural-language summary
    suitable for LLM system prompt injection.

    Parameters
    ----------
    weaknesses : list of dicts from detect_weaknesses()

    Returns
    -------
    str — compact 2-3 sentence summary, or empty string if no weaknesses
    """
    if not weaknesses:
        return ""

    parts = []
    for w in weaknesses:
        flag = w["flag"]
        severity = w["severity"]
        detail = w["detail"]
        sev_label = {1: "mild", 2: "moderate", 3: "severe"}.get(
            severity, ""
        )

        if flag == "FILLER_HABIT":
            parts.append(
                f"filler word habit ({sev_label}, {detail})"
            )
        elif flag == "PACE_ISSUE":
            parts.append(f"pace issue ({sev_label}, {detail})")
        elif flag == "HEDGING_HABIT":
            parts.append(
                f"hedging/uncertainty habit ({sev_label}, {detail})"
            )
        elif flag == "STUCK_WPM":
            parts.append("WPM not improving across recent sessions")
        elif flag == "STUCK_FILLERS":
            parts.append("filler count not decreasing across recent sessions")

    summary = "This user has: " + "; ".join(parts) + "."

    # Add actionable note
    high_severity = [w for w in weaknesses if w["severity"] >= 2]
    if high_severity:
        worst = max(high_severity, key=lambda w: w["severity"])
        summary += (
            f" Priority issue: {worst['flag'].replace('_', ' ').lower()}"
            f" (severity {worst['severity']}/3)."
        )

    return summary


def _compute_hedging_from_transcripts(sessions: list[dict], *, conn=None) -> float:
    """
    Compute average hedging signals per session by scanning stored
    transcripts from the turns table. Limited to last 5 sessions only.

    Uses the existing analyse_confidence() from engine/confidence.py
    to count hedging signals in each transcript.
    """
    if not sessions:
        return 0.0

    session_ids = [s["session_id"] for s in sessions if s.get("session_id")]
    if not session_ids:
        return 0.0

    with _use_conn(conn) as c:
        cursor = c.cursor()

        placeholders = ",".join("%s" for _ in session_ids)
        cursor.execute(f"""
            SELECT session_id, transcript
            FROM turns
            WHERE session_id IN ({placeholders})
            ORDER BY session_id, turn_number
        """, session_ids)
        rows = cursor.fetchall()

    if not rows:
        return 0.0

    # Group transcripts by session and count signals
    from collections import defaultdict
    session_signals = defaultdict(int)

    for session_id, transcript in rows:
        if transcript:
            result = analyse_confidence(transcript)
            session_signals[session_id] += result[
                "total_confidence_signals"
            ]

    if not session_signals:
        return 0.0

    return sum(session_signals.values()) / len(session_signals)


def _is_improving(values: list, lower_is_better: bool = False) -> bool:
    """
    Check if a metric is improving across a sequence of values.

    Returns True if the trend is positive (last value better than first).
    For lower_is_better metrics (like fillers), decreasing is improving.
    """
    if len(values) < 2:
        return True  # not enough data to judge

    first = values[0]
    last = values[-1]

    if first == 0:
        return True  # can't compute improvement from zero baseline

    change = (last - first) / first

    if lower_is_better:
        # Improving means decreasing — need negative change
        return change < -0.05  # 5% threshold
    else:
        # Improving means increasing
        return change > 0.05
