"""
pattern_discovery.py — Communication pattern discovery for ArticulateX.

Runs asynchronously after a session ends. Collects transcripts from
the last 5 sessions, sends them to the LLM to identify recurring
delivery patterns, and saves results to the user_patterns table.

This module makes LLM calls and MUST always run in a background thread
via asyncio.to_thread(). It must never block the main session flow.

Sprint 1: saves patterns to DB only — no dashboard display yet.
"""

import sqlite3
import json
from datetime import datetime

from core.memory import DB_PATH
from llm import call_llm


PATTERN_PROMPT = """Analyze these speaking transcripts from up to 5 practice sessions.
Identify exactly 2-3 recurring DELIVERY patterns in how this person communicates.

ONLY identify communication delivery patterns — not grammar, not content quality, not vocabulary.

Good examples of delivery patterns:
- "loses structure when challenged"
- "speeds up when uncertain"
- "starts strong then trails off"
- "uses filler bursts at transition points"
- "hedges before making strong claims"
- "repeats the same point when pressured"

Bad examples (do NOT return these):
- "good vocabulary" (content, not delivery)
- "grammatically correct" (grammar)
- "strong arguments" (content quality)

TRANSCRIPTS:
{transcripts}

Return ONLY a JSON array of 2-3 short pattern description strings.
Example: ["loses structure when challenged", "speeds up when uncertain"]

No explanation. No commentary. Just the JSON array."""


def discover_patterns(session_token: str) -> None:
    """
    Discover recurring communication patterns from recent sessions.

    This function is designed to be called via asyncio.to_thread()
    and must never be awaited directly in the request path.

    It collects transcripts from the last 5 completed sessions,
    sends them to the LLM for pattern analysis, and saves each
    discovered pattern to the user_patterns SQLite table.

    Parameters
    ----------
    session_token : str
        The session token that triggered this discovery.
        Used as a reference when saving patterns.
    """
    try:
        transcripts = _fetch_recent_transcripts()

        if not transcripts:
            print("[PATTERNS] No transcripts found — skipping discovery")
            return

        # Build transcript block for the prompt
        transcript_block = _format_transcripts(transcripts)

        prompt = PATTERN_PROMPT.format(transcripts=transcript_block)

        # Call LLM (this is the slow part — runs in background thread)
        print(f"[PATTERNS] Sending {len(transcripts)} sessions to LLM "
              f"for pattern discovery...")
        response = call_llm(prompt, temperature=0.3, max_tokens=200)

        # Parse patterns from LLM response
        patterns = _parse_patterns(response)

        if patterns:
            _save_patterns(session_token, patterns)
            print(f"[PATTERNS] Saved {len(patterns)} patterns: {patterns}")
        else:
            print("[PATTERNS] No valid patterns extracted from LLM response")

    except Exception as exc:
        # Never let pattern discovery crash anything
        print(f"[PATTERNS] Error during discovery: {exc}")


def _fetch_recent_transcripts() -> dict[int, list[str]]:
    """
    Fetch transcripts from the last 5 completed sessions.

    Returns
    -------
    dict mapping session_id → list of transcript strings
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get last 5 completed session IDs
    cursor.execute("""
        SELECT id FROM sessions
        WHERE total_turns > 0
        ORDER BY session_date DESC
        LIMIT 5
    """)
    session_ids = [row[0] for row in cursor.fetchall()]

    if not session_ids:
        conn.close()
        return {}

    placeholders = ",".join("?" for _ in session_ids)
    cursor.execute(f"""
        SELECT session_id, transcript
        FROM turns
        WHERE session_id IN ({placeholders})
        ORDER BY session_id, turn_number
    """, session_ids)

    from collections import defaultdict
    transcripts = defaultdict(list)
    for session_id, transcript in cursor.fetchall():
        if transcript and transcript.strip():
            transcripts[session_id].append(transcript.strip())

    conn.close()
    return dict(transcripts)


def _format_transcripts(transcripts: dict[int, list[str]]) -> str:
    """
    Format transcripts into a readable block for the LLM prompt.
    """
    parts = []
    for i, (session_id, turns) in enumerate(transcripts.items(), 1):
        combined = " | ".join(turns)
        # Limit each session's text to avoid token overflow
        if len(combined) > 800:
            combined = combined[:800] + "..."
        parts.append(f"Session {i}: {combined}")

    return "\n\n".join(parts)


def _parse_patterns(response: str) -> list[str]:
    """
    Parse the LLM response into a list of pattern strings.

    Handles various response formats:
    - Clean JSON array: ["pattern1", "pattern2"]
    - JSON with surrounding text
    - Numbered list fallback
    """
    # Try direct JSON parse
    response = response.strip()

    # Extract JSON array if embedded in text
    start = response.find("[")
    end = response.rfind("]")

    if start != -1 and end != -1 and end > start:
        json_str = response[start:end + 1]
        try:
            patterns = json.loads(json_str)
            if isinstance(patterns, list):
                # Filter to valid strings only
                return [
                    p.strip() for p in patterns
                    if isinstance(p, str) and len(p.strip()) > 5
                ][:3]  # cap at 3
        except json.JSONDecodeError:
            pass

    # Fallback: extract lines that look like pattern descriptions
    patterns = []
    for line in response.split("\n"):
        line = line.strip().strip("-•*").strip()
        # Skip empty lines and JSON artifacts
        if line and len(line) > 10 and not line.startswith(("{", "[")):
            # Remove leading numbers like "1." or "1)"
            import re
            line = re.sub(r'^\d+[.)]\s*', '', line).strip()
            if line and len(line) > 5:
                patterns.append(line[:100])  # cap length
            if len(patterns) >= 3:
                break

    return patterns


def _save_patterns(session_token: str, patterns: list[str]) -> None:
    """
    Save discovered patterns to the user_patterns table.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    for pattern_text in patterns:
        cursor.execute("""
            INSERT INTO user_patterns (session_token, pattern_text, discovered_at)
            VALUES (?, ?, ?)
        """, (session_token, pattern_text, now))

    conn.commit()
    conn.close()
