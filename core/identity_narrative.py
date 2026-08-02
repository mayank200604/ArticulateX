"""
identity_narrative.py — Voice identity and milestone narrative generation.

Runs asynchronously after a session ends (same pattern as pattern_discovery.py).
Both functions are blocking (LLM calls) and MUST be invoked via asyncio.to_thread().
"""

import json
from core.db import get_conn
from core.memory import (get_voice_identity, save_voice_identity,
                         get_milestone_narratives, save_milestone_narrative)
from core.user_memory import get_user_profile
from llm import call_llm


IDENTITY_PROMPT = """You are an expert communication coach analyzing a speaker's data after 5 sessions.
Based on the following data, generate a short, evocative "communication identity" label and a 1-2 sentence explanation.

Data:
- WPM Trend: {wpm_trend}
- Filler Trend: {filler_trend}
- Dominant Mode: {dominant_mode}
- Recurring Patterns: {patterns}

The label should be punchy and professional (e.g., "The Measured Persuader", "The Rapid-Fire Debater", "The Reflective Storyteller").
The explanation MUST be grounded in the provided data (e.g., mention their WPM trend, how they handle fillers, or their patterns). Use the second person ("You...").

Return ONLY valid JSON in this exact format, with no other text:
{{
  "label": "The Label Here",
  "description": "Your 1-2 sentence explanation here."
}}
"""

NARRATIVE_PROMPT = """You are an expert communication coach reviewing a speaker's progress after their {session_count}th session.
Write a short, engaging 3-5 sentence narrative about their communication journey so far. Use the second person ("You...").

Data:
- Sessions Completed: {session_count}
- WPM Trend: {wpm_trend}
- Filler Trend: {filler_trend}
- Dominant Mode: {dominant_mode}
- Recurring Patterns: {patterns}

Reflect on their progress, acknowledge their style, and encourage them to keep pushing. Make it sound like an earned milestone. Do NOT output JSON, just the narrative text.
"""


def _get_user_patterns(user_id: int) -> list[str]:
    """Fetch the user's most recent discovered patterns from user_patterns."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT pattern_text, MAX(discovered_at) as latest
            FROM user_patterns
            WHERE user_id = %s
            GROUP BY pattern_text
            ORDER BY latest DESC
            LIMIT 5
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows]


def generate_voice_identity(user_id: int) -> None:
    """
    Generate and save the voice identity after the 5th completed session.

    Guards:
    - Returns immediately if identity already exists for this user.
    - Returns immediately if user has fewer than 5 completed sessions.
    """
    try:
        if get_voice_identity(user_id):
            return  # Already generated — never regenerate

        profile = get_user_profile(user_id)
        if profile.get("total_sessions", 0) < 5:
            return  # Not enough sessions yet

        patterns = _get_user_patterns(user_id)

        prompt = IDENTITY_PROMPT.format(
            wpm_trend=profile.get("wpm_trend", "flat"),
            filler_trend=profile.get("filler_trend", "flat"),
            dominant_mode=profile.get("dominant_mode", "None"),
            patterns=", ".join(patterns) if patterns else "None detected yet",
        )

        print(f"[IDENTITY] Generating voice identity for user {user_id}...")
        response = call_llm(prompt, temperature=0.7, max_tokens=150)

        # Parse JSON from response (robust: find outermost braces)
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(response[start:end + 1])
            label = data.get("label", "The Communicator").strip()
            description = data.get("description",
                                   "You are finding your unique voice.").strip()
            save_voice_identity(user_id, label, description)
            print(f"[IDENTITY] Saved for user {user_id}: {label}")
        else:
            print(f"[IDENTITY] Failed to parse LLM response: {response}")

    except Exception as exc:
        print(f"[IDENTITY] Error generating voice identity: {exc}")


def generate_milestone_narrative(user_id: int, session_count: int) -> None:
    """
    Generate and save a milestone narrative at every 10th session.

    Guards:
    - Returns immediately if session_count is not a multiple of 10.
    - Returns immediately if a narrative already exists for this milestone.
    """
    try:
        if session_count == 0 or session_count % 10 != 0:
            return

        existing = get_milestone_narratives(user_id)
        if any(m["session_count"] == session_count for m in existing):
            return  # Already generated for this milestone

        profile = get_user_profile(user_id)
        patterns = _get_user_patterns(user_id)

        prompt = NARRATIVE_PROMPT.format(
            session_count=session_count,
            wpm_trend=profile.get("wpm_trend", "flat"),
            filler_trend=profile.get("filler_trend", "flat"),
            dominant_mode=profile.get("dominant_mode", "None"),
            patterns=", ".join(patterns) if patterns else "None detected yet",
        )

        print(f"[MILESTONE] Generating narrative for user {user_id} "
              f"at session {session_count}...")
        response = call_llm(prompt, temperature=0.7, max_tokens=250)
        narrative = response.strip()

        if narrative:
            save_milestone_narrative(user_id, session_count, narrative)
            print(f"[MILESTONE] Saved narrative for user {user_id} "
                  f"at session {session_count}")

    except Exception as exc:
        print(f"[MILESTONE] Error generating milestone narrative: {exc}")
