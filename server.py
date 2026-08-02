# -*- coding: utf-8 -*-
"""
server.py — ArticulateX FastAPI backend.
Serves the HTML frontend and all API endpoints.
Run with: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import json
import asyncio
import random
import time
import uuid

import numpy as np
import soundfile as sf
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import bcrypt
import psycopg2
import psycopg2.errors
from datetime import datetime

os.makedirs("audio_snapshots", exist_ok=True)

load_dotenv()

# ── Backend imports — unchanged from app.py ─────────────────────
from core.stt import transcribe, start_streaming_session, \
    stream_audio_chunk, stop_streaming_session, decode_audio_bytes
from core.tts import speak_to_file, TTS_OUTPUT_PATH
from core.analyser import analyse
from core.db import init_pool, get_conn
from core.memory import (init_db, create_session, save_turn,
    update_session_stats, get_all_sessions, get_progression_report,
    get_unlock_state, get_calibration_data)
from engine.confidence import analyse_confidence
from core.utils import is_audio_valid
from core.user_memory import get_user_profile
from core.weakness_detector import detect_weaknesses, format_weakness_summary
from core.pattern_discovery import discover_patterns
from core.identity_narrative import generate_voice_identity, \
    generate_milestone_narrative
from core.memory import get_voice_identity, get_milestone_narratives
from engine.conversation import (get_debate_response,
    get_freestyle_response, get_weird_situation_response,
    get_calibration_response)
from engine.unpredictability import (pick_strategy,
    STRATEGY_INSTRUCTIONS, Strategy)
from engine.feedback import generate_session_feedback
from engine.debate import (DEBATE_CONFIG, get_ai_side,
    assign_random_side)
from engine.freestyle import get_freestyle_prompt
from engine.weird_situation import get_weird_situation
from engine.topics import (DEBATE_LEVEL_1_TOPICS, DEBATE_LEVEL_2_TOPICS,
    DEBATE_LEVEL_3_TOPICS, FREESTYLE_TOPICS, FREESTYLE_WORDS, FREESTYLE_SCENARIOS)
from core.daily_quote import get_daily_quote

init_pool()
init_db()

# ── Calibration topics (hardcoded, gentle) ───────────────────
CALIBRATION_TOPICS = [
    "Tell me about something you enjoy doing in your free time.",
    "Describe your ideal weekend.",
    "What is a skill you would like to learn and why?",
    "Tell me about a place you have visited that you really liked.",
    "What is something that always makes you smile?",
    "Describe your favourite meal and why you love it.",
    "Tell me about a hobby or interest that you find relaxing.",
    "What kind of music do you enjoy and why?",
]



app = FastAPI(title="ArticulateX")

from starlette.middleware.sessions import SessionMiddleware

_session_secret = os.getenv("SESSION_SECRET")
if not _session_secret:
    raise RuntimeError(
        "SESSION_SECRET environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "and add it to your .env file."
    )
app.add_middleware(SessionMiddleware, secret_key=_session_secret)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# In-memory session store
SESSIONS: dict[str, dict] = {}

# ── Background task tracking ─────────────────────────────────────────
# Prevents fire-and-forget asyncio tasks from being GC'd mid-execution.
_background_tasks: set[asyncio.Task] = set()


def _persist_turn(sid: int, turn_data: dict, turns_snapshot: list) -> None:
    """Combined DB write: save turn then update session stats.

    Runs in a background thread via asyncio.to_thread().
    Guarantees save_turn() completes before update_session_stats()
    and halves the connection-pool overhead per turn.
    """
    try:
        save_turn(sid, turn_data)
        update_session_stats(sid, turns_snapshot)
    except Exception as e:
        print(f"[DB-ASYNC-ERROR] Failed to persist turn for session {sid}: {e}")


def _create_background_task(coro) -> asyncio.Task:
    """Create a tracked background task that won't be GC'd."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def new_session_token() -> str:
    return str(uuid.uuid4())


# ── Root → serve index.html ──────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))


# ── Serve TTS audio file ─────────────────────────────────────────
@app.get("/audio/response")
async def get_tts_audio():
    if os.path.exists(TTS_OUTPUT_PATH):
        return FileResponse(
            TTS_OUTPUT_PATH,
            media_type="audio/wav",
            headers={"Cache-Control": "no-cache, no-store"}
        )
    raise HTTPException(status_code=404, detail="No audio")


# ── Auth & Users ─────────────────────────────────────────────────
def get_current_user(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user_id

class AuthRequest(BaseModel):
    username: str
    password: str

@app.post("/api/register")
async def register(req: AuthRequest, request: Request):
    if len(req.username) < 3 or len(req.password) < 6:
        raise HTTPException(400, "Username min 3 chars, password min 6 chars")
    
    # bcrypt.gensalt() uses default cost factor 12
    hashed = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    
    with get_conn() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
                (req.username, hashed, datetime.now().isoformat())
            )
            user_id = cursor.fetchone()[0]
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            raise HTTPException(409, "Username already taken")
    
    request.session["user_id"] = user_id
    return JSONResponse({"ok": True, "username": req.username})

@app.post("/api/login")
async def login(req: AuthRequest, request: Request):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (req.username,))
        row = cursor.fetchone()
    
    if not row or not bcrypt.checkpw(req.password.encode(), row[1].encode()):
        raise HTTPException(401, "Invalid username or password")
    
    request.session["user_id"] = row[0]
    return JSONResponse({"ok": True, "username": req.username})

@app.get("/api/me")
async def me(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return JSONResponse({"logged_in": False})
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
    if not row:
        return JSONResponse({"logged_in": False})
    return JSONResponse({"logged_in": True, "username": row[0]})

@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})

@app.get("/api/daily_quote")
async def daily_quote(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Not logged in")
    data = get_daily_quote(user_id)
    return JSONResponse(data)


# ── Pydantic models ──────────────────────────────────────────────
class SetupRequest(BaseModel):
    mode: str            # freestyle|debate1|debate2|debate3|weird|calibration
    level: int = 0       # 1/2/3 for debate
    topic: str = ""
    user_side: str = ""  # for|against
    freestyle_type: str = ""  # word|scenario


class TurnRequest(BaseModel):
    session_token: str
    audio_b64: str       # base64 encoded WAV/WebM bytes
    sample_rate: int = 16000
    streaming_transcript: str = ""  # live transcript from WS STT (preserves fillers)


class FeedbackRequest(BaseModel):
    session_token: str


# ── Session setup ────────────────────────────────────────────────
class StartSessionRequest(BaseModel):
    session_token: str

@app.post("/api/start-session")
async def start_session(req: StartSessionRequest, request: Request):
    """
    Called when user actually begins the session (screen transition).
    Creates the database record for the session.
    """
    user_id = get_current_user(request)
    token = req.session_token
    if token in SESSIONS:
        sess = SESSIONS[token]
        if sess.get("session_id") is None:
            # Recompute mode_display for DB (e.g. FreeStyle, Debate Level 1)
            mode_display = {
                "freestyle": "FreeStyle",
                "debate1":   "Debate Level 1",
                "debate2":   "Debate Level 2",
                "debate3":   "Debate Level 3",
                "weird":     "Weird Situation",
                "calibration": "Calibration"
            }.get(sess["mode"], sess["mode"])
            
            sess["session_id"] = create_session(mode=mode_display, topic=sess["topic"], user_id=user_id)
            print(f"[START] Session DB row created for: {sess['topic']}")
    return JSONResponse({"status": "ok"})


@app.post("/api/setup")
async def setup_session(req: SetupRequest, request: Request):
    """
    Called when user clicks BEGIN SESSION.
    Creates a new session in DB and returns session token.
    """
    user_id = get_current_user(request)
    token = new_session_token()

    # ── Weird Situation mode is permanently disabled ──────────
    if req.mode == "weird":
        raise HTTPException(
            status_code=403,
            detail="Weird Situation mode is not yet available. "
                   "It will be unlocked in a future update."
        )

    # ── Calibration mode ─────────────────────────────────────
    if req.mode == "calibration":
        topic = random.choice(CALIBRATION_TOPICS)
        # session_id will be created during /api/start-session
        SESSIONS[token] = {
            "mode": "calibration",
            "level": 0,
            "topic": topic,
            "user_side": "",
            "ai_side": "",
            "session_id": None, # Will be created in /api/start-session
            "session_turns": [],
            "confidence_data": [],
            "history": [],
            "recent_strats": [],
            "topic_changed": False,
            "turn_number": 0,
            "full_report": "",
            "spoken_summary": "",
            "report_done": False,
            "max_turns": 3,
            "last_interrupt_rule": None,
            "consecutive_interrupts": 0,
        }
        print(f"[SETUP] Calibration session created: {topic}")
        return JSONResponse({
            "token": token,
            "topic": topic,
            "user_side": "",
            "ai_side": "",
            "level": 0,
            "mode": "calibration",
            "silence_seconds": None,
            "max_turns": 3,
        })

    # Determine ai_side
    ai_side = ""
    user_side = req.user_side
    if req.mode in ("debate1", "debate2", "debate3"):
        if req.mode == "debate3" and not user_side:
            user_side = assign_random_side()
        if not user_side:
            user_side = random.choice(["for", "against"])
        ai_side = get_ai_side(user_side)

    # Get topic
    topic = req.topic
    if not topic:
        if req.mode == "debate2":
            topic = random.choice(DEBATE_LEVEL_2_TOPICS)
        elif req.mode == "debate3":
            topic = random.choice(DEBATE_LEVEL_3_TOPICS)
        elif req.mode == "freestyle":
            if req.freestyle_type == "word":
                topic = random.choice(FREESTYLE_WORDS)
            elif req.freestyle_type == "scenario":
                topic = random.choice(FREESTYLE_SCENARIOS)
            else:
                topic = random.choice(FREESTYLE_TOPICS)
        elif req.mode == "weird":
            _, content, description = get_weird_situation()
            topic = description

    if not topic:
        topic = "General Discussion"

    # Create DB session
    mode_display = {
        "freestyle": "FreeStyle",
        "debate1":   "Debate Level 1",
        "debate2":   "Debate Level 2",
        "debate3":   "Debate Level 3",
        "weird":     "Weird Situation",
    }.get(req.mode, req.mode)

    # session_id will be created in /api/start-session
    
    # Store session state
    SESSIONS[token] = {
        "mode": req.mode,
        "level": req.level,
        "topic": topic,
        "user_side": user_side,
        "ai_side": ai_side,
        "session_id": None,
        "session_turns": [],
        "confidence_data": [],
        "history": [],
        "recent_strats": [],
        "topic_changed": False,
        "turn_number": 0,
        "full_report": "",
        "spoken_summary": "",
        "report_done": False,
        # ── Interrupt tracking (Changes 2 & 3) ───────────────
        "last_interrupt_rule": None,
        "consecutive_interrupts": 0,
        # ── Session Number for Milestones ────────────────────
        "session_number": 0,  # updated below
    }

    # ── Data Intelligence Layer (< 200ms, no LLM) ───────────────
    with get_conn() as conn_setup:
        profile = get_user_profile(user_id, conn=conn_setup)

        # Store session number based on completed sessions + 1
        # Calibration sessions do not increment the count
        session_number = profile.get("total_sessions", 0) + 1
        SESSIONS[token]["session_number"] = session_number

        weaknesses = detect_weaknesses(profile, conn=conn_setup)
        weakness_summary = format_weakness_summary(weaknesses)

        SESSIONS[token]["user_profile"] = profile
        SESSIONS[token]["weaknesses"] = weaknesses
        SESSIONS[token]["weakness_summary"] = weakness_summary

        if weakness_summary:
            print(f"[SETUP] User weaknesses: {weakness_summary}")
        else:
            print(f"[SETUP] No historical weaknesses detected "
                  f"(total sessions: {profile.get('total_sessions', 0)})")

        silence_map = {1: 4.0, 2: 3.0, 3: 2.0, 0: 3.0}

        debate3_count = 0
        if req.mode == "debate3":
            cur_d3 = conn_setup.cursor()
            cur_d3.execute(
                "SELECT COUNT(*) FROM sessions "
                "WHERE LOWER(mode) LIKE '%%debate%%3%%' AND total_turns > 0 AND user_id = %s",
                (user_id,)
            )
            debate3_count = cur_d3.fetchone()[0]

    return JSONResponse({
        "token": token,
        "topic": topic,
        "user_side": user_side,
        "ai_side": ai_side,
        "level": req.level,
        "mode": req.mode,
        "silence_seconds": silence_map.get(req.level, 3.0),
        "debate3_session_count": debate3_count,
    })


# ── Topics for debate level selection ────────────────────────────
_LEVEL_TOPIC_MAP = {
    1: DEBATE_LEVEL_1_TOPICS,
    2: DEBATE_LEVEL_2_TOPICS,
    3: DEBATE_LEVEL_3_TOPICS,
}


@app.get("/api/topics")
async def get_topics(level: int = 1):
    topics = _LEVEL_TOPIC_MAP.get(level, DEBATE_LEVEL_1_TOPICS)
    return JSONResponse({"topics": topics})


# ── Unlock state ─────────────────────────────────────────────────
@app.get("/api/unlock-state")
async def unlock_state(request: Request):
    """Returns current progressive unlock state for all modes."""
    user_id = get_current_user(request)
    return JSONResponse(get_unlock_state(user_id))


# ── Calibration report ───────────────────────────────────────────
@app.post("/api/calibration-report")
async def calibration_report(req: FeedbackRequest, request: Request):
    user_id = get_current_user(request)
    """
    Generate calibration report with baseline metrics and
    level recommendation. Separate from /api/feedback.
    """
    token = req.session_token
    if token not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    sess = SESSIONS[token]
    if sess["mode"] != "calibration":
        raise HTTPException(status_code=400, detail="Not a calibration session")

    session_id = sess.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="No session ID")

    # Compute hedging signals from in-memory confidence data
    total_hedging = sum(
        c.get("total_confidence_signals", 0)
        for c in sess.get("confidence_data", [])
    )

    cal_data = get_calibration_data(session_id)
    cal_data["hedging_signals"] = total_hedging

    return JSONResponse(cal_data)


# ── Weird situation ──────────────────────────────────────────────
@app.get("/api/weird-situation")
async def get_weird():
    display_type, content, description = get_weird_situation()
    return JSONResponse({
        "display_type": display_type,
        "content": content,
        "description": description,
    })


# ── Dashboard data ───────────────────────────────────────────────
@app.get("/api/dashboard")
async def get_dashboard(request: Request):
    user_id = get_current_user(request)
    sessions = await asyncio.to_thread(get_all_sessions, user_id)
    if not sessions:
        return JSONResponse({
            "total_sessions": 0,
            "total_turns": 0,
            "avg_wpm": 0,
            "avg_fillers": 0,
            "sessions": [],
        })

    def norm_mode(raw):
        raw = (raw or "").lower().strip()
        if "freestyle" in raw or "freeform" in raw:
            return "FreeStyle"
        if "level_3" in raw or "debate3" in raw or "debate level 3" in raw:
            return "Debate · Hard"
        if "level_2" in raw or "debate2" in raw or "debate level 2" in raw:
            return "Debate · Medium"
        if "level_1" in raw or "debate1" in raw or "debate level 1" in raw:
            return "Debate · Easy"
        if "weird" in raw:
            return "Weird Situation"
        return raw.title()

    total_sessions = len(sessions)
    total_turns = sum(s[4] or 0 for s in sessions)
    wpm_vals = [s[5] for s in sessions if s[5] and s[5] > 0]
    fil_vals = [s[6] for s in sessions if s[6] is not None]
    avg_wpm = round(sum(wpm_vals) / len(wpm_vals), 1) if wpm_vals else 0
    avg_fillers = round(sum(fil_vals) / len(fil_vals), 1) if fil_vals else 0

    sessions_chrono = list(reversed(sessions))
    session_data = []
    for i, s in enumerate(sessions_chrono, 1):
        session_data.append({
            "index": i,
            "date": (s[1] or "")[:10],
            "mode": norm_mode(s[2]),
            "topic": (s[3] or "")[:40],
            "turns": s[4] or 0,
            "wpm": round(s[5], 1) if s[5] else 0,
            "fillers": round(s[6], 1) if s[6] is not None else 0,
        })

    # Compute streak
    streak = 0
    if sessions:
        from datetime import date
        seen_dates = sorted(
            set(s[1][:10] for s in sessions if s[1]), reverse=True
        )
        today = date.today()
        for d in seen_dates:
            delta = (today - date.fromisoformat(d)).days
            if delta == streak:
                streak += 1
            else:
                break

    last_date = sessions[0][1][:10] if sessions and sessions[0][1] else "—"

    # Run progression + unlock on a single shared connection
    def _dashboard_db(uid):
        with get_conn() as conn:
            return {
                "progression": get_progression_report(uid, conn=conn),
                "unlock_state": get_unlock_state(uid, conn=conn),
            }

    db_data = await asyncio.to_thread(_dashboard_db, user_id)

    return JSONResponse({
        "total_sessions": total_sessions,
        "total_turns": total_turns,
        "avg_wpm": avg_wpm,
        "avg_fillers": avg_fillers,
        "sessions": session_data,
        "streak": streak,
        "last_date": last_date,
        "progression": db_data["progression"],
        "unlock_state": db_data["unlock_state"],
    })


# ── Pattern Dashboard ────────────────────────────────────────────
@app.get("/api/patterns")
async def get_patterns(request: Request):
    user_id = get_current_user(request)
    with get_conn() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE total_turns > 0 AND user_id = %s", (user_id,))
        session_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT DISTINCT pattern_text, MAX(discovered_at) as latest
            FROM user_patterns
            WHERE user_id = %s
            GROUP BY pattern_text
            ORDER BY latest DESC
            LIMIT 5
        """, (user_id,))
        rows = cursor.fetchall()
    
    return JSONResponse({
        "patterns": [row[0] for row in rows],
        "enough_sessions": session_count >= 5,
    })


# ── Voice Identity ───────────────────────────────────────────────
@app.get("/api/voice-identity")
async def api_get_voice_identity(request: Request):
    """Return the user's voice identity, or null if not yet earned."""
    user_id = get_current_user(request)
    identity = get_voice_identity(user_id)
    return JSONResponse({"identity": identity})


# ── Milestone Narratives ─────────────────────────────────────────
@app.get("/api/milestones")
async def api_get_milestones(request: Request):
    """Return all milestone narratives for the user, most recent first."""
    user_id = get_current_user(request)
    milestones = get_milestone_narratives(user_id)
    return JSONResponse({"milestones": milestones})


# ── Submit turn (main pipeline) ──────────────────────────────────
@app.post("/api/turn")
async def submit_turn(req: TurnRequest, request: Request = None):
    """
    Receives recorded audio as base64 WebM/WAV bytes.
    Runs full pipeline: STT → Analyse → LLM → TTS.
    Returns transcript, ai_response, metrics.
    TTS audio served separately at /audio/response.

    Supports X-Test-Mode header to skip TTS during automated testing.
    """
    # Check for test mode — skip TTS to save quota
    test_mode = False
    if request:
        test_mode = request.headers.get("x-test-mode", "").lower() == "true"
    import base64
    import io

    token = req.session_token
    if token not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    sess = SESSIONS[token]

    # Decode audio — browser sends WebM/Opus via MediaRecorder
    try:
        raw_bytes = base64.b64decode(req.audio_b64)
        audio_array, sr = decode_audio_bytes(raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Audio decode error: {exc}")

    if audio_array.ndim > 1:
        audio_array = audio_array[:, 0]
    peak = np.abs(audio_array).max()
    if peak > 1.0:
        audio_array = audio_array / peak

    # Validate
    valid, reason = is_audio_valid(audio_array, sr)
    if not valid:
        reason_map = {
            "too_short": "TOO SHORT — speak for at least 2 seconds",
            "too_quiet": "TOO QUIET — check your microphone",
            "no_variation": "NO SPEECH DETECTED — try again",
        }
        return JSONResponse({"error": reason_map.get(reason, "INVALID AUDIO")})

    # STT — prefer the streaming transcript sent by frontend
    # (preserves filler words from AssemblyAI real-time).
    # Fallback chain: streaming_transcript → stop_streaming_session() → batch transcribe()
    transcript = ""
    detected_fillers = []  # populated only by batch AssemblyAI path

    if req.streaming_transcript and len(req.streaming_transcript.split()) >= 3:
        # Clean trailing ellipsis marker from live partials
        transcript = req.streaming_transcript.rstrip("…").strip()
        print(f"[TURN] Using streaming transcript (fillers preserved): "
              f"{transcript[:80]}")
    else:
        transcript = stop_streaming_session()
        if transcript:
            print(f"[TURN] Using stop_streaming_session(): {transcript[:80]}")

    if not transcript or len(transcript.split()) < 3:
        stt_result = transcribe(audio_array, sr)
        transcript = stt_result["transcript"]
        detected_fillers = stt_result.get("detected_fillers", [])
        print(f"[TURN] Batch fallback transcript: {transcript[:80]}")
        if detected_fillers:
            print(f"[TURN] AssemblyAI detected fillers: {detected_fillers}")

    if not transcript or len(transcript.split()) < 5:
        return JSONResponse({"error": "TOO SHORT — speak a full sentence"})

    # Analyse
    duration = len(audio_array) / max(sr, 1)
    analysis = analyse(transcript, duration, detected_fillers=detected_fillers)
    conf = analyse_confidence(transcript)

    mode = sess["mode"]
    level = sess["level"]
    topic = sess["topic"]
    user_side = sess["user_side"]
    ai_side = sess["ai_side"]
    history = sess["history"]
    recent_strats = sess["recent_strats"]
    topic_changed = sess["topic_changed"]
    turn_number = sess["turn_number"]

    just_did_redo = False
    if level == 3 and analysis["total_fillers"] > 5:
        just_did_redo = True

    # LLM response
    ai_response = ""
    is_interrupt = False
    calibration_complete = False

    # Get weakness context for this session
    weakness_ctx = sess.get("weakness_summary", "")

    if mode == "calibration":
        # Calibration mode — gentle follow-up, no pressure
        ai_response = get_calibration_response(
            topic, history, transcript, turn_number + 1
        )
        max_turns = sess.get("max_turns", 3)
        if turn_number + 1 >= max_turns:
            calibration_complete = True

    elif mode in ("debate1", "debate2", "debate3"):
        strategy = pick_strategy(
            recent_strats, analysis, level,
            turn_number + 1, topic_changed, just_did_redo
        )
        strategy_instr = STRATEGY_INSTRUCTIONS[strategy]

        ai_response = get_debate_response(
            topic, user_side, ai_side, level,
            history, transcript, strategy_instr, turn_number + 1,
            weakness_ctx
        )
        sess["recent_strats"] = (recent_strats + [strategy])[-6:]
        if strategy == Strategy.CHANGE_TOPIC:
            sess["topic_changed"] = True

    elif mode == "freestyle":
        fs_type = "word" if len(topic.split()) == 1 else "scenario"
        ai_response = get_freestyle_response(
            fs_type, topic, history, transcript, weakness_ctx
        )

    elif mode == "weird":
        ai_response = get_weird_situation_response(
            topic, history, transcript, weakness_ctx
        )

    # TTS — skip in test mode to save Google Cloud TTS quota
    audio_ready = False
    if ai_response and not test_mode:
        path = speak_to_file(ai_response)
        audio_ready = path is not None and os.path.exists(path)

    # Update session state
    new_turn_number = turn_number + 1
    wpm_val = analysis["wpm"]
    fil_count = analysis["total_fillers"]
    conf_sig = conf["total_confidence_signals"]

    turn_data = {
        "turn_number": new_turn_number,
        "transcript": transcript,
        "wpm": wpm_val,
        "filler_count": fil_count,
        "filler_words": analysis["filler_words"],
        "avg_sentence_length": analysis["avg_sentence_length"],
        "duration_seconds": duration,
        "word_count": analysis["word_count"],
        "held_position": analysis["has_clear_opening_position"],
        "used_evidence": False,
        "asked_question": "?" in transcript,
    }

    # ── Audio Snapshot (Before and After) ──
    if turn_number == 0:
        _create_background_task(
            asyncio.to_thread(
                check_and_save_snapshot,
                sess["session_id"],
                sess.get("session_number", 0),
                raw_bytes  # Use raw base64-decoded bytes
            )
        )

    sess["session_turns"].append(turn_data)
    sess["confidence_data"].append(conf)
    sess["history"].append({"role": "user", "content": transcript})
    sess["history"].append({"role": "assistant", "content": ai_response})
    sess["turn_number"] = new_turn_number

    # ── Dynamic pressure: clean turn resets consecutive counter ──
    sess["consecutive_interrupts"] = 0

    sid = sess.get("session_id")
    if sid and sid > 0:
        _create_background_task(
            asyncio.to_thread(
                _persist_turn, sid, turn_data,
                sess["session_turns"][:]
            )
        )

    return JSONResponse({
        "transcript": transcript,
        "ai_response": ai_response,
        "audio_ready": audio_ready,
        "is_interrupt": is_interrupt,
        "turn_number": new_turn_number,
        "wpm": wpm_val,
        "fillers": fil_count,
        "confidence_signals": conf_sig,
        "just_did_redo": just_did_redo,
        "calibration_complete": calibration_complete,
        "error": None,
    })


# ── Generate feedback ────────────────────────────────────────────
@app.post("/api/feedback")
async def get_feedback(req: FeedbackRequest, request: Request):
    user_id = get_current_user(request)
    token = req.session_token
    if token not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    sess = SESSIONS[token]
    session_turns = sess["session_turns"]

    if not session_turns:
        return JSONResponse({"error": "No turns recorded"})

    if not sess["report_done"]:
        mode_display = {
            "freestyle": "FreeStyle",
            "debate1":   "Debate Level 1",
            "debate2":   "Debate Level 2",
            "debate3":   "Debate Level 3",
            "weird":     "Weird Situation",
        }.get(sess["mode"], sess["mode"])

        result = generate_session_feedback(
            sess["session_id"],
            session_turns,
            mode_display,
            sess["topic"],
            sess["confidence_data"],
            sess["level"],
            user_profile=sess.get("user_profile"),
        )

        if isinstance(result, tuple):
            full_report, spoken_summary = result
        else:
            full_report = result
            spoken_summary = ""

        # Extract spoken summary from report if not returned separately
        if not spoken_summary and full_report:
            lines = full_report.split("\n")
            in_summary = False
            summary_lines = []
            for line in lines:
                if line.strip() == "SPOKEN SUMMARY":
                    in_summary = True
                    continue
                if in_summary:
                    summary_lines.append(line)
            spoken_summary = " ".join(summary_lines).strip()

        sess["full_report"] = full_report
        sess["spoken_summary"] = spoken_summary
        sess["report_done"] = True

    avg_wpm = round(
        sum(t["wpm"] for t in session_turns) / len(session_turns), 1
    )
    avg_fil = round(
        sum(t["filler_count"] for t in session_turns) / len(session_turns), 1
    )
    total_conf = sum(
        c.get("total_confidence_signals", 0)
        for c in sess["confidence_data"]
    )

    # ── Adaptive difficulty recommendation (debate modes only) ─
    next_recommendation = ""
    mode = sess["mode"]
    level = sess["level"]
    if mode in ("debate1", "debate2", "debate3"):
        unlock = get_unlock_state(user_id)
        if mode == "debate1" and avg_fil < 3 and avg_wpm > 120 and unlock["debate2"]:
            next_recommendation = "You are ready for Level 2 — try it next session."
        elif mode == "debate2" and avg_fil < 2 and avg_wpm > 130 and unlock["debate3"]:
            next_recommendation = "You are ready for Level 3 — try it next session."
        elif mode == "debate3":
            next_recommendation = "Stay at Level 3 — this is your growth zone."
        else:
            next_recommendation = "Stay at your current level for one more session."

    resp = JSONResponse({
        "full_report": sess["full_report"],
        "spoken_summary": sess["spoken_summary"],
        "total_turns": len(session_turns),
        "avg_wpm": avg_wpm,
        "avg_fillers": avg_fil,
        "total_fillers": sum(t["filler_count"] for t in session_turns),
        "total_confidence_signals": total_conf,
        "mode": sess["mode"],
        "topic": sess["topic"],
        "level": sess["level"],
        "next_recommendation": next_recommendation,
        "milestone_playback": get_milestone_snapshots(sess["session_id"], sess["session_number"]),
    })

    # ── Trigger async pattern discovery (background, non-blocking) ─
    _create_background_task(
        asyncio.to_thread(discover_patterns, token, user_id)
    )

    # ── Trigger async voice identity + milestone narrative generation ─
    _create_background_task(
        asyncio.to_thread(generate_voice_identity, user_id)
    )
    if sess.get("session_number", 0) > 0 and sess["session_number"] % 10 == 0:
        _create_background_task(
            asyncio.to_thread(
                generate_milestone_narrative, user_id, sess["session_number"]
            )
        )

    return resp


# ── Play spoken summary ──────────────────────────────────────────
@app.post("/api/play-summary")
async def play_summary(req: FeedbackRequest, request: Request):
    user_id = get_current_user(request)
    token = req.session_token
    if token not in SESSIONS:
        raise HTTPException(status_code=404)
    sess = SESSIONS[token]
    text = sess.get("spoken_summary", "")
    if text:
        speak_to_file(text)
        return JSONResponse({"audio_ready": True})
    return JSONResponse({"audio_ready": False})


# ── Play full report ─────────────────────────────────────────────
@app.post("/api/play-report")
async def play_report(req: FeedbackRequest, request: Request):
    user_id = get_current_user(request)
    token = req.session_token
    if token not in SESSIONS:
        raise HTTPException(status_code=404)
    sess = SESSIONS[token]
    text = (sess.get("full_report", "") or "")[:800]
    if text:
        speak_to_file(text)
        return JSONResponse({"audio_ready": True})
    return JSONResponse({"audio_ready": False})


# ── Interrupt rule engine ────────────────────────────────────────
import re as _re

# Filler set imported from analyser for consistency
_DEFINITE_FILLERS = {
    "um", "uh", "ah", "er", "eh", "like", "basically",
    "literally", "honestly", "you know", "i mean",
    "kind of", "sort of", "i think", "i guess",
    "you see", "okay so", "anyway"
}

_EVIDENCE_KEYWORDS = {
    "for example", "for instance", "such as", "because",
    "data", "research", "study", "evidence", "proves",
    "statistics", "fact", "reason", "proof", "shows",
}

_OPENING_PHRASES = [
    "i believe", "i think", "i argue", "my view",
    "in my opinion", "i would say", "my point is",
    "the reason",
]

# ── Weighted scoring (Change 1) ──────────────────────────────────
# Base weights per rule — sum to 1.0 when all breach simultaneously
_RULE_WEIGHTS = {
    "word_overload": 0.65,
    "filler_overload": 0.65,
    "claim_no_evidence": 0.35,
}
_INTERRUPT_SCORE_THRESHOLD = 0.6

# ── Dynamic word-overload thresholds per debate level ────────────
# Lower thresholds at higher levels account for AssemblyAI
# transcript lag at high speaking speeds.
_WORD_OVERLOAD_THRESHOLDS = {
    1: 60,   # Level 1 — lenient
    2: 55,   # Level 2 — moderate
    3: 45,   # Level 3 — aggressive
}
_WORD_OVERLOAD_DEFAULT = 50  # fallback for non-debate / unknown level



def _count_definite_fillers(text: str) -> int:
    """Count definite filler words using word-boundary regex."""
    text_lower = text.lower()
    total = 0
    for filler in _DEFINITE_FILLERS:
        total += len(_re.findall(
            r'\b' + _re.escape(filler) + r'\b', text_lower
        ))
    return total


def evaluate_interrupt_rules(transcript: str, level: int = 0) -> str | None:
    """
    Legacy single-rule evaluator — kept for backward compatibility
    with non-WS callers. Returns the first breached rule or None.
    """
    if not transcript or not transcript.strip():
        return None

    clean = transcript.rstrip("…").strip()
    text_lower = clean.lower()
    words = text_lower.split()
    word_count = len(words)

    word_threshold = _WORD_OVERLOAD_THRESHOLDS.get(
        level, _WORD_OVERLOAD_DEFAULT
    )
    if word_count > word_threshold:
        return "word_overload"
    filler_count = _count_definite_fillers(text_lower)
    if filler_count >= 5:
        return "filler_overload"
    if word_count >= 30:
        has_opening = any(p in text_lower for p in _OPENING_PHRASES)
        has_evidence = any(k in text_lower for k in _EVIDENCE_KEYWORDS)
        if has_opening and not has_evidence:
            return "claim_no_evidence"
    return None


def evaluate_interrupt_weighted(
    transcript: str,
    level: int = 0,
) -> tuple[dict, float, str | None]:
    """
    Weighted interrupt scoring system (Change 1).

    Evaluates all three rules, computes a combined weighted score,
    and returns:
        breached  — dict of rule_name → True/False
        score     — combined float 0..1
        top_rule  — name of the highest-weighted breached rule
                     (used for interrupt message selection)

    The word_overload threshold is level-dependent:
    L1=60, L2=55, L3=45 words.
    """
    breached: dict[str, bool] = {
        "word_overload": False,
        "filler_overload": False,
        "claim_no_evidence": False,
    }

    if not transcript or not transcript.strip():
        return breached, 0.0, None

    clean = transcript.rstrip("…").strip()
    text_lower = clean.lower()
    words = text_lower.split()
    word_count = len(words)

    # Rule 1 — Word count overload (rambling)
    # Threshold varies by debate level
    word_threshold = _WORD_OVERLOAD_THRESHOLDS.get(
        level, _WORD_OVERLOAD_DEFAULT
    )
    if word_count > word_threshold:
        breached["word_overload"] = True

    # Rule 2 — Filler overload
    filler_count = _count_definite_fillers(text_lower)
    if filler_count >= 5:
        breached["filler_overload"] = True

    # Rule 3 — Claim without evidence (only after 30+ words)
    if word_count >= 30:
        has_opening = any(p in text_lower for p in _OPENING_PHRASES)
        has_evidence = any(k in text_lower for k in _EVIDENCE_KEYWORDS)
        if has_opening and not has_evidence:
            breached["claim_no_evidence"] = True

    # Calculate combined weighted score
    score = 0.0
    best_rule = None
    best_weight = -1.0

    for rule_name, is_breached in breached.items():
        if not is_breached:
            continue

        weight = _RULE_WEIGHTS[rule_name]

        score += weight

        if weight > best_weight:
            best_weight = weight
            best_rule = rule_name

    breached_names = [r for r, b in breached.items() if b]
    if breached_names:
        print(
            f"[WS-INT] Weighted score: {score:.2f} "
            f"(threshold={_INTERRUPT_SCORE_THRESHOLD}) "
            f"breached={breached_names}"
        )

    return breached, score, best_rule


_INTERRUPT_MESSAGES = {
    "word_overload": (
        "You are going on too long without landing a point. "
        "What is your actual argument in one sentence?"
    ),
    "filler_overload": (
        "Too many filler words. Stop. "
        "Say your point again without the ums and likes."
    ),
    "claim_no_evidence": (
        "You made a claim but gave nothing to back it up. "
        "Why should I believe what you just said?"
    ),
}


# ── WebSocket for real-time STT streaming ────────────────────────
@app.websocket("/ws/stt")
async def websocket_stt(ws: WebSocket):
    """
    Browser connects here when user starts recording.
    Sends raw PCM Int16 chunks as binary frames.
    Server forwards to AssemblyAI and sends back
    partial transcript text as text frames.

    Accepts ?session_token=<token> to enable mid-speech
    interrupt evaluation during debate modes.
    """
    await ws.accept()
    print("[WS-STT] Client connected")

    # ── Session awareness ────────────────────────────────────────
    token = ws.query_params.get("session_token", "")
    sess = SESSIONS.get(token)
    level = sess["level"] if sess else 0
    mode = sess["mode"] if sess else ""
    is_debate = mode in ("debate1", "debate2", "debate3")
    interrupt_fired = False

    # Only evaluate interrupts for debate modes with probability > 0
    can_interrupt = (
        is_debate
        and level >= 2
        and sess is not None
    )
    print(f"[WS-STT] session_token={'...' + token[-8:] if token else 'none'}, "
          f"mode={mode}, level={level}, can_interrupt={can_interrupt}")

    loop = asyncio.get_event_loop()

    import threading

    def _start():
        success = start_streaming_session()
        asyncio.run_coroutine_threadsafe(
            ws.send_text(json.dumps({
                "type": "ready" if success else "fallback",
            })),
            loop
        )

    threading.Thread(target=_start, daemon=True).start()

    chunk_count = 0
    last_log_words = 0  # track word count at last log to avoid spam

    try:
        while True:
            data = await ws.receive()

            if "bytes" in data:
                chunk_count += 1
                raw_pcm = data["bytes"]
                pcm_array = np.frombuffer(raw_pcm, dtype=np.int16)
                float_array = pcm_array.astype(np.float32) / 32768.0

                current_transcript = stream_audio_chunk(float_array, 16000)
                if current_transcript:
                    await ws.send_text(json.dumps({
                        "type": "partial",
                        "text": current_transcript,
                    }))

                    # ── Interrupt evaluation (weighted scoring) ──
                    if can_interrupt and not interrupt_fired:
                        # Strip trailing ellipsis before evaluation
                        # (get_current_transcript appends "…" to
                        # partials which can break word-boundary
                        # regex for fillers at end of string)
                        clean_transcript = current_transcript.rstrip("…").strip()
                        word_count = len(clean_transcript.split())
                        filler_count = _count_definite_fillers(clean_transcript)

                        # Log every 50 chunks or when word count jumps by 10+
                        if (chunk_count % 50 == 0
                                or word_count >= last_log_words + 10):
                            last_log_words = word_count
                            print(
                                f"[WS-INT] chunk={chunk_count} "
                                f"words={word_count} "
                                f"fillers={filler_count} "
                                f"transcript=\"{clean_transcript[-60:]}\""
                            )

                        # weighted scoring
                        breached, score, top_rule = (
                            evaluate_interrupt_weighted(
                                clean_transcript,
                                level=level,
                            )
                        )

                        import time
                        if score >= _INTERRUPT_SCORE_THRESHOLD and top_rule:
                            print(f"[WS-INT-DEBUG] {time.time():.3f} — evaluate_interrupt_weighted breached threshold ({score:.2f})")
                            # Change 3: dynamic pressure adjustment
                            # — reduce probability after 3 consecutive
                            #   interrupted turns
                            base_prob = DEBATE_CONFIG[level][
                                "interrupt_probability"
                            ]
                            consec = sess.get(
                                "consecutive_interrupts", 0
                            )
                            pressure_reduction = (
                                0.10 if consec >= 3 else 0.0
                            )
                            prob = max(
                                base_prob - pressure_reduction, 0.0
                            )

                            if pressure_reduction > 0:
                                print(
                                    f"[WS-INT] Pressure reduced: "
                                    f"base={base_prob:.0%} → "
                                    f"{prob:.0%} "
                                    f"(consecutive={consec})"
                                )

                            if random.random() < prob:
                                interrupt_fired = True
                                rule = top_rule
                                print(
                                    f"[WS-STT] ⚡ INTERRUPT fired: "
                                    f"rule={rule}, score={score:.2f}, "
                                    f"level={level}"
                                )

                                # Update interrupt tracking
                                sess["consecutive_interrupts"] = (
                                    consec + 1
                                )

                                # ── Fast-path signal to frontend ──
                                print(f"[WS-INT-DEBUG] {time.time():.3f} — sending interrupt_start via ws.send_text")
                                await ws.send_text(json.dumps({
                                    "type": "interrupt_start",
                                    "rule": rule
                                }))

                                # Stop the STT stream immediately
                                final_transcript = stop_streaming_session()
                                partial = final_transcript or current_transcript

                                # Generate AI interrupt response
                                # via asyncio.to_thread to avoid
                                # blocking the event loop
                                strategy_instr = STRATEGY_INSTRUCTIONS[
                                    Strategy.INTERRUPT_REDIRECT
                                ]
                                print(f"[WS-INT-DEBUG] {time.time():.3f} — asyncio.to_thread for LLM starts")
                                ai_response = await asyncio.to_thread(
                                    get_debate_response,
                                    sess["topic"],
                                    sess["user_side"],
                                    sess["ai_side"],
                                    level,
                                    sess["history"],
                                    partial,
                                    strategy_instr,
                                    sess["turn_number"] + 1,
                                    weakness_context="",
                                    interrupt_rule=rule
                                )
                                print(f"[WS-INT-DEBUG] {time.time():.3f} — asyncio.to_thread for LLM ends")

                                # Generate TTS
                                audio_ready = False
                                tts_path = await asyncio.to_thread(
                                    speak_to_file, ai_response
                                )
                                if tts_path and os.path.exists(tts_path):
                                    audio_ready = True

                                # ── Save interrupted turn ────────
                                new_turn = sess["turn_number"] + 1
                                duration = len(partial.split()) / 2.5
                                analysis = analyse(partial, duration)
                                conf = analyse_confidence(partial)

                                turn_data = {
                                    "turn_number": new_turn,
                                    "transcript": partial,
                                    "wpm": analysis["wpm"],
                                    "filler_count": analysis["total_fillers"],
                                    "filler_words": analysis["filler_words"],
                                    "avg_sentence_length": analysis[
                                        "avg_sentence_length"
                                    ],
                                    "duration_seconds": duration,
                                    "word_count": analysis["word_count"],
                                    "held_position": analysis[
                                        "has_clear_opening_position"
                                    ],
                                    "used_evidence": False,
                                    "asked_question": "?" in partial,
                                }

                                # ── Audio Snapshot (Before and After) ──
                                if sess["turn_number"] == 0:
                                    _create_background_task(
                                        asyncio.to_thread(
                                            check_and_save_snapshot,
                                            sess["session_id"],
                                            sess.get("session_number", 0),
                                            raw_pcm
                                        )
                                    )

                                sess["session_turns"].append(turn_data)
                                sess["confidence_data"].append(conf)
                                sess["history"].append({
                                    "role": "user", "content": partial
                                })
                                sess["history"].append({
                                    "role": "assistant",
                                    "content": ai_response,
                                })
                                sess["turn_number"] = new_turn
                                sess["recent_strats"] = (
                                    sess["recent_strats"]
                                    + [Strategy.INTERRUPT_REDIRECT]
                                )[-6:]

                                sid = sess.get("session_id")
                                if sid and sid > 0:
                                    _create_background_task(
                                        asyncio.to_thread(
                                            _persist_turn, sid, turn_data,
                                            sess["session_turns"][:]
                                        )
                                    )

                                # ── Send interrupt to frontend ───
                                print(f"[WS-INT-DEBUG] {time.time():.3f} — sending final interrupt via ws.send_text")
                                await ws.send_text(json.dumps({
                                    "type": "interrupt",
                                    "rule": rule,
                                    "transcript": partial,
                                    "ai_response": ai_response,
                                    "audio_ready": audio_ready,
                                    "turn_number": new_turn,
                                    "wpm": analysis["wpm"],
                                    "fillers": analysis["total_fillers"],
                                    "confidence_signals": conf[
                                        "total_confidence_signals"
                                    ],
                                }))
                                print(f"[WS-STT] Interrupt sent to "
                                      f"client, closing WS")
                                break  # exit WS loop

            elif "text" in data:
                msg = json.loads(data["text"])
                if msg.get("action") == "stop":
                    final = stop_streaming_session()
                    await ws.send_text(json.dumps({
                        "type": "final",
                        "text": final or "",
                    }))
                    break

    except WebSocketDisconnect:
        print("[WS-STT] Client disconnected")
    except Exception as exc:
        print(f"[WS-STT] Error: {exc}")
    finally:
        try:
            stop_streaming_session()
        except Exception:
            pass


# ── Run ──────────────────────────────────────────────────────────
@app.get("/audio/snapshot/{filename}")
async def get_snapshot_audio(filename: str):
    """Serve a raw audio snapshot."""
    file_path = os.path.join("audio_snapshots", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(file_path, media_type="audio/wav")


def check_and_save_snapshot(session_id: int, session_number: int, audio_data: bytes):
    """
    Save a proper WAV from the first turn if this is session 1
    or a 10th session milestone (10, 20, 30...).
    Uses the persistent database session_id for filenames so
    before/after snapshots can be matched across sessions.
    Runs asynchronously via asyncio.to_thread().
    """
    try:
        # Check if we need to record a snapshot for this session
        if session_number == 1 or session_number % 10 == 0:
            filename = f"session_{session_id}.wav"
            file_path = os.path.join("audio_snapshots", filename)

            # Never overwrite an existing snapshot
            if not os.path.exists(file_path):
                # Decode to float32 numpy array, then write proper WAV
                audio_array, sr = decode_audio_bytes(audio_data)
                if audio_array.ndim > 1:
                    audio_array = audio_array[:, 0]
                sf.write(file_path, audio_array, sr)
                print(f"[SNAPSHOT] Saved milestone snapshot: {filename}")
    except Exception as exc:
        print(f"[SNAPSHOT] Failed to save snapshot: {exc}")


def get_milestone_snapshots(session_id: int, session_number: int) -> dict | None:
    """
    Return before and after URLs if this session completes a milestone.
    Uses persistent session_id for filename matching.
    Example: For session 10, before = session 1, after = session 10.
             For session 20, before = session 10, after = session 20.
    """
    if session_number > 0 and session_number % 10 == 0:
        before_num = 1 if session_number == 10 else session_number - 10
        before_filename = f"session_{session_id - (session_number - before_num)}.wav"
        after_filename = f"session_{session_id}.wav"

        before_path = os.path.join("audio_snapshots", before_filename)
        after_path = os.path.join("audio_snapshots", after_filename)

        if os.path.exists(before_path) and os.path.exists(after_path):
            return {
                "before_url": f"/audio/snapshot/{before_filename}",
                "after_url": f"/audio/snapshot/{after_filename}"
            }
    return None

if __name__ == "__main__":
    import uvicorn
    # Initialize snapshot dir
    os.makedirs("audio_snapshots", exist_ok=True)
    print("\n" + "=" * 50)
    print("  ARTICULATEX — AI Communication Coach")
    print("  http://localhost:8000")
    print("=" * 50 + "\n")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
