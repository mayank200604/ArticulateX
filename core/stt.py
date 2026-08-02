# core/stt.py
# Requires: pip install -U assemblyai   (v0.40+ for streaming.v3)
"""
Speech-to-text.
Primary:  AssemblyAI Universal-2 (disfluency enabled)
Fallback: Groq Whisper large-v3
"""

import os
import io
import tempfile
import numpy as np
import soundfile as sf
from dotenv import load_dotenv
import threading
import queue

load_dotenv()

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


def decode_audio_bytes(raw_bytes: bytes, sample_rate: int = 16000) -> tuple:
    """
    Decode any browser audio format (WebM/Opus, OGG, MP4, WAV) to
    a float32 numpy array using ffmpeg.
    Returns (audio_array, sample_rate).
    Raises RuntimeError if ffmpeg is not available or decoding fails.
    """
    import subprocess

    # Try soundfile first (fast path for plain WAV)
    try:
        buf = io.BytesIO(raw_bytes)
        arr, sr = sf.read(buf, dtype="float32", always_2d=False)
        if arr.ndim > 1:
            arr = arr[:, 0]
        return arr, sr
    except Exception:
        pass  # Not a format soundfile understands — fall through to ffmpeg

    # ffmpeg decode to 16kHz mono PCM s16le
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", "pipe:0",           # read from stdin
                "-vn",                     # no video
                "-acodec", "pcm_s16le",
                "-ar", str(sample_rate),
                "-ac", "1",               # mono
                "-f", "s16le",
                "pipe:1",                 # write raw PCM to stdout
            ],
            input=raw_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed: {result.stderr.decode(errors='replace')[-500:]}"
            )
        pcm = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
        pcm /= 32768.0
        return pcm, sample_rate
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found. Install it: choco install ffmpeg  OR  winget install ffmpeg"
        )


def _array_to_wav_bytes(audio_array: np.ndarray,
                         sample_rate: int) -> bytes:
    """Convert numpy float32 audio to WAV bytes in memory."""
    buf = io.BytesIO()
    sf.write(buf, audio_array, sample_rate, format="WAV",
             subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def _transcribe_assemblyai(audio_array: np.ndarray,
                            sample_rate: int) -> dict:
    """
    Transcribe using AssemblyAI Universal-2.
    disfluencies=True keeps um, uh, like, you know etc.
    Returns a dict with 'transcript' (str) and
    'detected_fillers' (list of filler word strings
    extracted from AssemblyAI word-level data).
    """
    import assemblyai as aai

    aai.settings.api_key = ASSEMBLYAI_API_KEY

    # Write to temp WAV file — AssemblyAI needs a file path
    with tempfile.NamedTemporaryFile(suffix=".wav",
                                     delete=False) as tmp:
        tmp_path = tmp.name
        sf.write(tmp_path, audio_array, sample_rate)

    try:
        config = aai.TranscriptionConfig(
            speech_model=aai.SpeechModel.best,
            disfluencies=True,       # keep um, uh, like etc
            language_code="en",
            punctuate=True,
            format_text=True,
        )
        transcriber = aai.Transcriber(config=config)
        result = transcriber.transcribe(tmp_path)

        if result.status == aai.TranscriptStatus.error:
            raise RuntimeError(result.error)

        text = (result.text or "").strip()

        # ── Extract disfluency tokens from word-level data ───────
        detected_fillers = []
        try:
            # AssemblyAI returns word-level data in result.words
            # Each word may have a 'type' field ('text' or 'filler')
            # depending on SDK version and config.
            words = getattr(result, 'words', None) or []
            for w in words:
                # Method 1: word.type == 'filler' (newer SDK)
                w_type = getattr(w, 'type', None) or ''
                if str(w_type).lower() == 'filler':
                    w_text = getattr(w, 'text', '') or ''
                    if w_text.strip():
                        detected_fillers.append(w_text.strip().lower())
                    continue
                # Method 2: word.speaker_confidence or
                # word metadata marking disfluencies
                w_text = getattr(w, 'text', '') or ''
                # Some SDK versions use a 'confidence' below
                # threshold for disfluencies — not reliable,
                # so we only use explicit type markers above.

            # Method 3: check for separate disfluencies field
            disfluencies = getattr(result, 'disfluencies', None)
            if disfluencies and isinstance(disfluencies, list):
                for d in disfluencies:
                    d_text = ''
                    if isinstance(d, str):
                        d_text = d.strip().lower()
                    elif hasattr(d, 'text'):
                        d_text = (d.text or '').strip().lower()
                    if d_text:
                        detected_fillers.append(d_text)

            if detected_fillers:
                print(f"[STT] AssemblyAI disfluencies: {detected_fillers}")
        except Exception as exc:
            print(f"[STT] Disfluency extraction warning: {exc}")

        return {
            "transcript": text,
            "detected_fillers": detected_fillers,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _transcribe_groq(audio_array: np.ndarray,
                     sample_rate: int) -> str:
    """
    Fallback: Groq Whisper large-v3.
    Note: strips filler words by design.
    """
    from groq import Groq

    client = Groq(api_key=GROQ_API_KEY)

    wav_bytes = _array_to_wav_bytes(audio_array, sample_rate)

    transcription = client.audio.transcriptions.create(
        model="whisper-large-v3",
        file=("audio.wav", wav_bytes, "audio/wav"),
        language="en",
        response_format="text",
    )
    return (transcription or "").strip()


def transcribe(audio_array: np.ndarray,
               sample_rate: int = 16000) -> dict:
    """
    Public transcription function.
    Tries AssemblyAI first, falls back to Groq Whisper.
    Returns a dict with:
        'transcript' — str (empty string on failure)
        'detected_fillers' — list of filler words extracted
                             from AssemblyAI word-level data
                             (empty list when Groq is used or
                              extraction fails)
    """
    empty_result = {"transcript": "", "detected_fillers": []}

    if not isinstance(audio_array, np.ndarray):
        return empty_result

    # Ensure mono float32
    arr = audio_array.astype(np.float32)
    if arr.ndim > 1:
        arr = arr[:, 0]
    peak = np.abs(arr).max()
    if peak > 1.0:
        arr = arr / peak

    # Primary — Groq Whisper (In-Memory, <1s latency)
    if GROQ_API_KEY:
        try:
            result = _transcribe_groq(arr, sample_rate)
            if result:
                print(f"[STT] Groq Whisper: {result[:80]}...")
                return {"transcript": result, "detected_fillers": []}
        except Exception as exc:
            print(f"[STT] Groq Whisper failed: {exc}, falling back to AssemblyAI")

    # Fallback — AssemblyAI (Slower, Batch API)
    if ASSEMBLYAI_API_KEY:
        try:
            result = _transcribe_assemblyai(arr, sample_rate)
            if result["transcript"]:
                print(f"[STT] AssemblyAI: {result['transcript'][:80]}...")
                return result
        except Exception as exc:
            print(f"[STT] AssemblyAI failed ({exc})")

    print("[STT] All providers failed — returning empty string")
    return empty_result


class StreamingSTTSession:
    """
    Manages one real-time STT session using AssemblyAI Streaming v3.
    Connects to wss://streaming.assemblyai.com/v3/ws
    """

    SAMPLE_RATE = 16000

    def __init__(self):
        self._finals: list[str] = []
        self._partial: str = ""
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._client = None
        self._started = False
        self._error: str | None = None
        self._thread = None

    def start(self) -> bool:
        if not ASSEMBLYAI_API_KEY:
            print("[STT-RT] No ASSEMBLYAI_API_KEY")
            return False
        try:
            from assemblyai.streaming.v3 import (
                StreamingClient,
                StreamingClientOptions,
                StreamingEvents,
                StreamingParameters,
                TurnEvent,
                BeginEvent,
                TerminationEvent,
                StreamingError,
            )

            self._client = StreamingClient(
                StreamingClientOptions(
                    api_key=ASSEMBLYAI_API_KEY,
                    connect_timeout=5.0,
                    max_connection_retries=4,
                    connection_retry_delay=1.0,
                )
            )

            def on_begin(client, event: BeginEvent):
                print(f"[STT-RT] Session started: {event.id}")
                self._ready.set()

            def on_turn(client, event: TurnEvent):
                with self._lock:
                    if event.end_of_turn:
                        if event.transcript:
                            self._finals.append(event.transcript)
                        self._partial = ""
                    else:
                        self._partial = event.transcript or ""

            def on_terminated(client, event: TerminationEvent):
                print(f"[STT-RT] Session terminated: {event.audio_duration_seconds}s")

            def on_error(client, error: StreamingError):
                error_code = getattr(error, 'code', 'UNKNOWN')
                print(f"[STT-RT] Error: {error} (code: {error_code})")
                self._error = str(error)
                self._ready.set()

            self._client.on(StreamingEvents.Begin, on_begin)
            self._client.on(StreamingEvents.Turn, on_turn)
            self._client.on(StreamingEvents.Termination, on_terminated)
            self._client.on(StreamingEvents.Error, on_error)

            # connect() blocks — run in background thread
            def _connect():
                try:
                    self._client.connect(
                        StreamingParameters(
                            sample_rate=self.SAMPLE_RATE,
                            speech_model="u3-rt-pro",  # required — no default
                            format_turns=True,
                        )
                    )
                except Exception as exc:
                    print(f"[STT-RT] connect thread error: {exc}")
                    self._error = str(exc)
                    self._ready.set()

            self._thread = threading.Thread(target=_connect, daemon=True)
            self._thread.start()

            connected = self._ready.wait(timeout=10)
            if not connected or self._error:
                print(f"[STT-RT] Could not connect: {self._error or 'timeout'}")
                try:
                    self._client.disconnect(terminate=True)
                except Exception:
                    pass
                self._client = None
                return False

            self._started = True
            print("[STT-RT] Connected successfully (v3)")
            return True

        except ImportError:
            print("[STT-RT] assemblyai.streaming.v3 not available — update SDK: pip install -U assemblyai")
            return False
        except Exception as exc:
            print(f"[STT-RT] Failed to start: {exc}")
            self._client = None
            return False

    def send_chunk(self, audio_array: np.ndarray, sample_rate: int) -> None:
        if not self._started or self._client is None:
            return
        try:
            arr = audio_array.astype(np.float32)
            if arr.ndim > 1:
                arr = arr[:, 0]
            if sample_rate != self.SAMPLE_RATE:
                import scipy.signal as sig
                ratio = self.SAMPLE_RATE / sample_rate
                arr = sig.resample(arr, int(len(arr) * ratio))
            # Must be 50ms–1000ms chunks per AssemblyAI v3 requirement
            pcm = (arr * 32767).astype(np.int16).tobytes()
            self._client.stream(pcm)
        except Exception as exc:
            print(f"[STT-RT] send_chunk error: {exc}")

    def get_current_transcript(self) -> str:
        with self._lock:
            parts = self._finals.copy()
            if self._partial:
                parts.append(self._partial + "…")
            return " ".join(parts)

    def stop(self) -> str:
        final = ""
        try:
            if self._client:
                self._client.disconnect(terminate=True)
            with self._lock:
                final = " ".join(self._finals).strip()
        except Exception as exc:
            print(f"[STT-RT] stop error: {exc}")
        self._started = False
        self._client = None
        return final


# Module-level session — one per recording turn
_active_session: StreamingSTTSession | None = None
_session_lock = threading.Lock()


def start_streaming_session() -> bool:
    """
    Start a new real-time STT session.
    Call this when the user begins recording.
    Returns True if session started successfully.
    """
    global _active_session
    with _session_lock:
        if _active_session is not None:
            try:
                _active_session.stop()
            except Exception:
                pass
            _active_session = None
        try:
            _active_session = StreamingSTTSession()
            success = _active_session.start()
            if not success:
                _active_session = None
                print("[STT-RT] Streaming unavailable "
                      "— batch STT will be used")
            return success
        except Exception as exc:
            print(f"[STT-RT] start_streaming_session "
                  f"error: {exc}")
            _active_session = None
            return False


def stream_audio_chunk(audio_array: np.ndarray,
                        sample_rate: int) -> str:
    """
    Send one audio chunk to the active session.
    Returns current live transcript string.
    Call this for every Gradio streaming chunk.
    """
    global _active_session
    with _session_lock:
        if _active_session is None:
            return ""
        _active_session.send_chunk(audio_array, sample_rate)
        return _active_session.get_current_transcript()


def stop_streaming_session() -> str:
    """
    Stop the active session and return the final transcript.
    Call this when the user stops recording.
    Falls back to batch transcribe() if streaming failed.
    """
    global _active_session
    with _session_lock:
        if _active_session is None:
            return ""
        final = _active_session.stop()
        _active_session = None
        return final
