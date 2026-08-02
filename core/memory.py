import psycopg2
import psycopg2.errors
import json
from contextlib import contextmanager
from datetime import datetime

from core.db import get_conn


@contextmanager
def _use_conn(conn=None):
    """Yield the provided connection, or check one out from the pool."""
    if conn is not None:
        yield conn  # caller owns the lifecycle — no commit/rollback here
    else:
        with get_conn() as new_conn:
            yield new_conn


def init_db():
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                session_date TEXT,
                mode TEXT,
                topic TEXT,
                total_turns INTEGER,
                avg_wpm REAL,
                avg_filler_count REAL,
                summary TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id SERIAL PRIMARY KEY,
                session_id INTEGER,
                turn_number INTEGER,
                transcript TEXT,
                wpm REAL,
                filler_count INTEGER,
                filler_words TEXT,
                avg_sentence_length REAL,
                duration_seconds REAL,
                word_count INTEGER,
                held_position INTEGER,
                used_evidence INTEGER,
                asked_question INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_patterns (
                id SERIAL PRIMARY KEY,
                session_token TEXT NOT NULL,
                pattern_text TEXT NOT NULL,
                discovered_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS voice_identity (
                id SERIAL PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                identity_label TEXT NOT NULL,
                identity_description TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestone_narratives (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_count_at_milestone INTEGER NOT NULL,
                narrative_text TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, session_count_at_milestone)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_quotes (
                user_id INTEGER PRIMARY KEY,
                last_quote_shown_date TEXT,
                last_quote_id INTEGER,
                recent_quote_ids TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # ── Schema migrations (safe to re-run) ───────────────────
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'sessions' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE sessions ADD COLUMN user_id INTEGER REFERENCES users(id);
                END IF;
            END $$;
        """)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'user_patterns' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE user_patterns ADD COLUMN user_id INTEGER REFERENCES users(id);
                END IF;
            END $$;
        """)


def save_session(mode: str, topic: str, turns: list) -> int:
    with get_conn() as conn:
        cursor = conn.cursor()

        avg_wpm = sum(t["wpm"] for t in turns) / max(len(turns), 1)
        avg_fillers = sum(t["filler_count"] for t in turns) / max(len(turns), 1)

        cursor.execute("""
            INSERT INTO sessions 
            (session_date, mode, topic, total_turns, avg_wpm, avg_filler_count)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            datetime.now().isoformat(),
            mode,
            topic,
            len(turns),
            round(avg_wpm, 1),
            round(avg_fillers, 1)
        ))

        session_id = cursor.fetchone()[0]

        for turn in turns:
            cursor.execute("""
                INSERT INTO turns
                (session_id, turn_number, transcript, wpm, filler_count,
                 filler_words, avg_sentence_length, duration_seconds,
                 word_count, held_position, used_evidence, asked_question)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                turn["turn_number"],
                turn["transcript"],
                turn["wpm"],
                turn["filler_count"],
                json.dumps(turn["filler_words"]),
                turn["avg_sentence_length"],
                turn["duration_seconds"],
                turn["word_count"],
                1 if turn["held_position"] else 0,
                1 if turn["used_evidence"] else 0,
                1 if turn["asked_question"] else 0
            ))

        return session_id


def get_session(session_id: int) -> dict:
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM sessions WHERE id=%s", 
            (session_id,)
        )
        session = cursor.fetchone()

        cursor.execute(
            "SELECT * FROM turns WHERE session_id=%s ORDER BY turn_number",
            (session_id,)
        )
        turns = cursor.fetchall()

        return {"session": session, "turns": turns}


def get_all_sessions(user_id: int = None, *, conn=None) -> list:
    with _use_conn(conn) as c:
        cursor = c.cursor()
        cursor.execute(
            "SELECT * FROM sessions WHERE user_id = %s ORDER BY session_date DESC",
            (user_id,)
        )
        sessions = cursor.fetchall()
        return sessions


def save_turn(session_id: int, turn_data: dict, *, conn=None) -> None:
    """Saves a single turn immediately after it happens."""
    with _use_conn(conn) as c:
        cursor = c.cursor()
        cursor.execute("""
            INSERT INTO turns
            (session_id, turn_number, transcript, wpm, 
             filler_count, filler_words, avg_sentence_length,
             duration_seconds, word_count, held_position,
             used_evidence, asked_question)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session_id,
            turn_data["turn_number"],
            turn_data["transcript"],
            turn_data["wpm"],
            turn_data["filler_count"],
            json.dumps(turn_data["filler_words"]),
            turn_data["avg_sentence_length"],
            turn_data["duration_seconds"],
            turn_data["word_count"],
            1 if turn_data["held_position"] else 0,
            1 if turn_data["used_evidence"] else 0,
            1 if turn_data["asked_question"] else 0
        ))


def create_session(mode: str, topic: str, user_id: int = None) -> int:
    """Creates a session entry at start and returns session_id."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions
            (session_date, mode, topic, total_turns, 
             avg_wpm, avg_filler_count, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            datetime.now().isoformat(),
            mode,
            topic,
            0,
            0.0,
            0.0,
            user_id
        ))
        session_id = cursor.fetchone()[0]
        return session_id


def update_session_stats(session_id: int, turns: list, *, conn=None) -> None:
    """Updates session summary stats after every turn."""
    if not turns:
        return
    with _use_conn(conn) as c:
        cursor = c.cursor()
        avg_wpm = sum(t["wpm"] for t in turns) / len(turns)
        avg_fillers = sum(t["filler_count"] for t in turns) / len(turns)
        cursor.execute("""
            UPDATE sessions 
            SET total_turns=%s, avg_wpm=%s, avg_filler_count=%s
            WHERE id=%s
        """, (len(turns), round(avg_wpm, 1), round(avg_fillers, 1), session_id))


def check_database_status() -> None:
    """Prints a summary of what is stored in the database."""
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sessions")
        session_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM turns")
        turn_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT session_date, mode, topic, total_turns 
            FROM sessions 
            ORDER BY session_date DESC 
            LIMIT 3
        """)
        recent = cursor.fetchall()

    print("\n─────────────────────────────────")
    print(f"DATABASE STATUS")
    print(f"Total sessions stored : {session_count}")
    print(f"Total turns stored    : {turn_count}")
    if recent:
        print(f"Last 3 sessions:")
        for r in recent:
            print(f"  [{r[0][:10]}] {r[1]} — {r[2]} ({r[3]} turns)")
    else:
        print("No sessions stored yet.")
    print("─────────────────────────────────\n")


def get_progression_report(user_id: int = None, *, conn=None) -> dict:
    """
    Month-over-month comparison of communication metrics.
    Called only from /api/dashboard — never during live sessions.
    No session_token needed; operates on global session history.

    Returns
    -------
    dict with keys: this_month, last_month, trends
    """
    from datetime import datetime, timedelta

    now = datetime.now()
    first_of_this_month = now.replace(day=1, hour=0, minute=0,
                                      second=0, microsecond=0)
    first_of_last_month = (first_of_this_month - timedelta(days=1)).replace(day=1)

    this_month_start = first_of_this_month.isoformat()
    last_month_start = first_of_last_month.isoformat()
    last_month_end = first_of_this_month.isoformat()

    with _use_conn(conn) as c:
        cursor = c.cursor()

        # This month
        cursor.execute("""
            SELECT AVG(avg_wpm), AVG(avg_filler_count), COUNT(*)
            FROM sessions
            WHERE session_date >= %s AND total_turns > 0 AND user_id = %s
        """, (this_month_start, user_id))
        tm = cursor.fetchone()

        # Last month
        cursor.execute("""
            SELECT AVG(avg_wpm), AVG(avg_filler_count), COUNT(*)
            FROM sessions
            WHERE session_date >= %s AND session_date < %s AND total_turns > 0 AND user_id = %s
        """, (last_month_start, last_month_end, user_id))
        lm = cursor.fetchone()

    this_month = {
        "avg_wpm": round(tm[0], 1) if tm[0] else 0,
        "avg_fillers": round(tm[1], 1) if tm[1] else 0,
        "sessions": tm[2] or 0,
    }
    last_month = {
        "avg_wpm": round(lm[0], 1) if lm[0] else 0,
        "avg_fillers": round(lm[1], 1) if lm[1] else 0,
        "sessions": lm[2] or 0,
    }

    def _trend(current: float, previous: float,
               lower_is_better: bool = False) -> str:
        """Compute trend label with 10% threshold."""
        if previous == 0:
            return "STABLE" if current == 0 else "IMPROVING"
        change = (current - previous) / previous
        if lower_is_better:
            change = -change  # invert: decrease is improvement
        if change >= 0.10:
            return "IMPROVING"
        elif change <= -0.10:
            return "DECLINING"
        return "STABLE"

    trends = {
        "wpm": _trend(this_month["avg_wpm"], last_month["avg_wpm"]),
        "fillers": _trend(this_month["avg_fillers"],
                          last_month["avg_fillers"],
                          lower_is_better=True),
        "sessions": _trend(this_month["sessions"],
                           last_month["sessions"]),
    }

    return {
        "this_month": this_month,
        "last_month": last_month,
        "trends": trends,
    }


def get_unlock_state(user_id: int = None, *, conn=None) -> dict:
    """
    Compute progressive unlock states from session history.

    Called on every home screen load and from /api/dashboard.
    No separate unlock table — derived fresh from session counts.
    All 3 internal queries run on the same connection.

    Returns
    -------
    dict with boolean unlock flags and remaining counts.
    """
    with _use_conn(conn) as c:
        cursor = c.cursor()

        # Calibration complete (or if user has any historical sessions)
        cursor.execute(
            "SELECT COUNT(*) FROM sessions "
            "WHERE total_turns > 0 AND user_id = %s",
            (user_id,)
        )
        calibration_done = cursor.fetchone()[0] > 0

        # Debate Level 1 completed sessions (LIKE for legacy compat)
        cursor.execute(
            "SELECT COUNT(*) FROM sessions "
            "WHERE LOWER(mode) LIKE '%%debate%%1%%' AND total_turns > 0 AND user_id = %s",
            (user_id,)
        )
        debate1_count = cursor.fetchone()[0]

        # Debate Level 2 completed sessions
        cursor.execute(
            "SELECT COUNT(*) FROM sessions "
            "WHERE LOWER(mode) LIKE '%%debate%%2%%' AND total_turns > 0 AND user_id = %s",
            (user_id,)
        )
        debate2_count = cursor.fetchone()[0]

    # Unlock rules
    freestyle_unlocked = calibration_done
    debate1_unlocked = calibration_done
    debate2_unlocked = debate1_count >= 3
    debate3_unlocked = debate2_count >= 2
    weird_unlocked = False  # Permanently locked — will be enabled in a future update

    return {
        "calibration_done": calibration_done,
        "freestyle": freestyle_unlocked,
        "debate1": debate1_unlocked,
        "debate2": debate2_unlocked,
        "debate3": debate3_unlocked,
        "weird": weird_unlocked,
        "debate2_remaining": max(0, 3 - debate1_count),
        "debate3_remaining": max(0, 2 - debate2_count),
    }


def get_calibration_data(session_id: int) -> dict:
    """
    Build the calibration report from a completed calibration session.

    Parameters
    ----------
    session_id : int
        The session ID of the calibration session.

    Returns
    -------
    dict with baseline metrics and recommended starting level.
    """
    with get_conn() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT wpm, filler_count, filler_words "
            "FROM turns WHERE session_id = %s ORDER BY turn_number",
            (session_id,)
        )
        rows = cursor.fetchall()

    if not rows:
        return {
            "avg_wpm": 0,
            "avg_fillers": 0,
            "most_common_filler": "none",
            "hedging_signals": 0,
            "recommended_level": 1,
        }

    wpms = [r[0] or 0 for r in rows]
    fillers = [r[1] or 0 for r in rows]
    avg_wpm = round(sum(wpms) / len(wpms), 1)
    avg_fillers = round(sum(fillers) / len(fillers), 1)

    # Most common filler word
    filler_counter: dict[str, int] = {}
    for r in rows:
        try:
            filler_list = json.loads(r[2]) if r[2] else []
        except (json.JSONDecodeError, TypeError):
            filler_list = []
        for fw in filler_list:
            if isinstance(fw, dict):
                word = fw.get("word", "")
                count = fw.get("count", 1)
            else:
                word = str(fw)
                count = 1
            if word:
                filler_counter[word] = filler_counter.get(word, 0) + count

    most_common_filler = "none"
    if filler_counter:
        most_common_filler = max(filler_counter, key=filler_counter.get)

    # Hedging signal count (placeholder — confidence analysis
    # is done at turn time, not stored in turns table)
    hedging_signals = 0

    # Recommendation logic
    # Level 3 is NEVER recommended at calibration
    if avg_fillers > 5 or avg_wpm < 100:
        recommended_level = 1
    else:
        # avg_fillers 3–5 or WPM 100–130 → Level 2
        # avg_fillers < 3 and WPM > 130  → still Level 2
        recommended_level = 2

    return {
        "avg_wpm": avg_wpm,
        "avg_fillers": avg_fillers,
        "most_common_filler": most_common_filler,
        "hedging_signals": hedging_signals,
        "recommended_level": recommended_level,
    }


def get_voice_identity(user_id: int) -> dict | None:
    """Return the user's voice identity, or None if not yet generated."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT identity_label, identity_description, generated_at "
            "FROM voice_identity WHERE user_id = %s",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return {"label": row[0], "description": row[1], "generated_at": row[2]}
        return None


def save_voice_identity(user_id: int, label: str, description: str) -> None:
    """Insert voice identity. No-op if one already exists (UNIQUE constraint)."""
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO voice_identity
                (user_id, identity_label, identity_description, generated_at)
                VALUES (%s, %s, %s, %s)
            """, (user_id, label, description, datetime.now().isoformat()))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()  # Clear aborted transaction state


def get_milestone_narratives(user_id: int) -> list:
    """Return all milestone narratives for a user, most recent first."""
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_count_at_milestone, narrative_text, generated_at
            FROM milestone_narratives
            WHERE user_id = %s
            ORDER BY session_count_at_milestone DESC
        """, (user_id,))
        rows = cursor.fetchall()
        return [
            {"session_count": r[0], "narrative": r[1], "generated_at": r[2]}
            for r in rows
        ]


def save_milestone_narrative(user_id: int, session_count: int,
                             narrative_text: str) -> None:
    """Insert milestone narrative. No-op if this milestone already exists."""
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO milestone_narratives
                (user_id, session_count_at_milestone, narrative_text, generated_at)
                VALUES (%s, %s, %s, %s)
            """, (user_id, session_count, narrative_text,
                  datetime.now().isoformat()))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()  # Clear aborted transaction state
