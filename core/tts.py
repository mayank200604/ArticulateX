# core/tts.py
"""
Text-to-speech.
Primary: Google Cloud WaveNet (low latency, generous free tier)
"""

import os
import re
import tempfile
from dotenv import load_dotenv

load_dotenv()

GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "")

# WaveNet voice — en-IN-Wavenet-D is Indian English male
# Options: en-IN-Wavenet-A (female), en-IN-Wavenet-D (male)
# en-US-Wavenet-D for American neutral
WAVENET_VOICE     = os.getenv("GOOGLE_TTS_VOICE", "en-IN-Wavenet-D")
WAVENET_LANGUAGE  = os.getenv("GOOGLE_TTS_LANGUAGE", "en-IN")
TTS_OUTPUT_PATH   = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "tts_output.wav"
)
MAX_CHARS = 4500   # Google TTS limit per request is 5000 bytes


def clean_for_tts(text: str) -> str:
    """Remove punctuation that TTS would read aloud."""
    text = text.replace("...", " ")
    text = text.replace("..", " ")
    text = re.sub(r'\s([.,!?;:"])\s', ' ', text)
    text = re.sub(r'\s([.,!?;:"])$', '', text)
    text = re.sub(r'^([.,!?;:"])\s', '', text)
    text = re.sub(r'(?<!\w)[.,;:"](?!\w)', '', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


def _chunk_text(text: str, max_chars: int = MAX_CHARS) -> list:
    """Split text into chunks under max_chars at sentence boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 <= max_chars:
            current = (current + " " + s).lstrip()
        else:
            if current:
                chunks.append(current)
            current = s
    if current:
        chunks.append(current)
    return chunks or [text[:max_chars]]


def _synthesise_google(text: str) -> bytes | None:
    """
    Call Google Cloud TTS REST API with API key.
    Returns raw MP3 bytes or None on failure.
    """
    import requests, base64

    url = (
        "https://texttospeech.googleapis.com/v1/text:synthesize"
        f"?key={GOOGLE_TTS_API_KEY}"
    )
    payload = {
        "input":  {"text": text},
        "voice":  {
            "languageCode": WAVENET_LANGUAGE,
            "name":         WAVENET_VOICE,
            "ssmlGender":   "MALE",
        },
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
            "speakingRate": 1.05,   # slightly faster feels natural
            "pitch": 0.0,
        },
    }
    resp = requests.post(url, json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    audio_b64 = data.get("audioContent", "")
    if not audio_b64:
        return None
    return base64.b64decode(audio_b64)


def speak_to_file(text: str) -> str | None:
    """
    Convert text to speech and save to tts_output.wav.
    Returns the file path on success, None on failure.
    """
    if not text or not text.strip():
        return None

    text = clean_for_tts(text)

    if not GOOGLE_TTS_API_KEY:
        print("[TTS] No GOOGLE_TTS_API_KEY found in .env")
        return None

    try:
        import numpy as np
        import soundfile as sf

        chunks  = _chunk_text(text)
        all_pcm = []

        for chunk in chunks:
            raw = _synthesise_google(chunk)
            if raw is None:
                continue
            # raw is LINEAR16 WAV bytes — decode to numpy
            import io
            pcm_array, sr = sf.read(io.BytesIO(raw), dtype="float32")
            all_pcm.append(pcm_array)

        if not all_pcm:
            return None

        import numpy as np
        full_audio = np.concatenate(all_pcm)
        sf.write(TTS_OUTPUT_PATH, full_audio, 24000)
        print(f"[TTS] Google WaveNet -> {TTS_OUTPUT_PATH}")
        return TTS_OUTPUT_PATH

    except Exception as exc:
        print(f"[TTS] Google WaveNet error: {exc}")
        return None
