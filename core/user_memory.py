"""
user_memory.py — Long-term user memory for ArticulateX.

Provides get_user_profile() which runs at session start to build
a compact profile dict from the last 5 completed sessions.

Performance target: < 200ms. Pure SQL + Python — zero LLM calls.
"""

from core.db import get_conn
from core.memory import _use_conn


def get_user_profile(user_id: int, *, conn=None) -> dict:
    """
    Build a compact user profile from historical session data.

    Queries the last 5 completed sessions (total_turns > 0) from
    PostgreSQL and computes trends, dominant mode, and averages.

    Parameters
    ----------
    user_id : int
        The authenticated user's ID. All queries are scoped
        to sessions belonging to this user.
    conn : connection, optional
        An existing DB connection to reuse. If None, a new one
        is checked out from the pool.

    Returns
    -------
    dict with keys:
        total_sessions, last_5_sessions, wpm_trend, filler_trend,
        dominant_mode, most_played_level, avg_wpm, avg_fillers
    """
    with _use_conn(conn) as c:
        cursor = c.cursor()

        # Total completed sessions
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE total_turns > 0 AND user_id = %s",
            (user_id,)
        )
        total_sessions = cursor.fetchone()[0]

        # Last 5 completed sessions (most recent first)
        cursor.execute("""
            SELECT id, session_date, mode, avg_wpm, avg_filler_count
            FROM sessions
            WHERE total_turns > 0 AND user_id = %s
            ORDER BY session_date DESC
            LIMIT 5
        """, (user_id,))
        rows = cursor.fetchall()

        # Dominant mode across all completed sessions
        cursor.execute("""
            SELECT mode, COUNT(*) as cnt
            FROM sessions
            WHERE total_turns > 0 AND user_id = %s
            GROUP BY mode
            ORDER BY cnt DESC
            LIMIT 1
        """, (user_id,))
        mode_row = cursor.fetchone()
        dominant_mode = mode_row[0] if mode_row else "None"

    if not rows:
        return {
            "total_sessions": 0,
            "last_5_sessions": [],
            "wpm_trend": "flat",
            "filler_trend": "flat",
            "dominant_mode": "None",
            "most_played_level": "None",
            "avg_wpm": 0,
            "avg_fillers": 0,
        }

    # Build session list (chronological order for trend calc)
    last_5 = []
    for row in reversed(rows):  # oldest first
        last_5.append({
            "session_id": row[0],
            "date": (row[1] or "")[:10],
            "mode": row[2] or "",
            "avg_wpm": row[3] or 0,
            "avg_fillers": row[4] or 0,
        })

    # Compute averages across last 5
    wpm_values = [s["avg_wpm"] for s in last_5 if s["avg_wpm"] > 0]
    filler_values = [s["avg_fillers"] for s in last_5]

    avg_wpm = round(sum(wpm_values) / len(wpm_values), 1) if wpm_values else 0
    avg_fillers = round(
        sum(filler_values) / len(filler_values), 1
    ) if filler_values else 0

    # Compute trends: compare first half vs second half
    # Labels track raw metric direction: "declining" = value going down.
    # For WPM, declining is bad (slower).  For fillers, declining is good (fewer).
    wpm_trend = _compute_trend(
        [s["avg_wpm"] for s in last_5], filter_zeros=True
    )
    filler_trend = _compute_trend(
        [s["avg_fillers"] for s in last_5]
    )

    # Most played level (extract from mode strings)
    most_played_level = _extract_most_played_level(
        [s["mode"] for s in last_5]
    )

    return {
        "total_sessions": total_sessions,
        "last_5_sessions": last_5,
        "wpm_trend": wpm_trend,
        "filler_trend": filler_trend,
        "dominant_mode": dominant_mode,
        "most_played_level": most_played_level,
        "avg_wpm": avg_wpm,
        "avg_fillers": avg_fillers,
    }


def _compute_trend(values: list, *, filter_zeros: bool = False) -> str:
    """
    Compute trend from a chronological list of metric values.

    Compares average of the earlier half vs the later half.
    Labels track the *raw metric direction*:
        later half ≥ 10% higher → 'improving'  (value going up)
        later half ≥ 10% lower  → 'declining'  (value going down)
        otherwise               → 'flat'

    The caller decides what the direction means contextually:
    - WPM declining  → user is getting slower  (bad)
    - fillers declining → user uses fewer fillers (good)
    """
    if len(values) < 2:
        return "flat"

    # Optionally filter zeros (e.g. WPM sessions with no speech data)
    if filter_zeros:
        values = [v for v in values if v > 0]
        if len(values) < 2:
            return "flat"

    mid = len(values) // 2
    early_avg = sum(values[:mid]) / max(mid, 1)
    late_avg = sum(values[mid:]) / max(len(values) - mid, 1)

    if early_avg == 0:
        return "flat" if late_avg == 0 else "improving"

    change = (late_avg - early_avg) / early_avg

    if change >= 0.10:
        return "improving"
    elif change <= -0.10:
        return "declining"
    return "flat"


def _extract_most_played_level(modes: list) -> str:
    """
    Extract the most commonly played level from mode strings.

    Mode strings are like 'Debate Level 1', 'FreeStyle',
    'Weird Situation', etc.
    """
    from collections import Counter

    level_map = {
        "debate level 1": "Debate Level 1",
        "debate level 2": "Debate Level 2",
        "debate level 3": "Debate Level 3",
        "freestyle": "FreeStyle",
        "weird situation": "Weird Situation",
    }

    normalised = []
    for mode in modes:
        key = mode.lower().strip()
        for pattern, label in level_map.items():
            if pattern in key:
                normalised.append(label)
                break

    if not normalised:
        return "None"

    counts = Counter(normalised)
    return counts.most_common(1)[0][0]
