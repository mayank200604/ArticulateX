import numpy as np
import sounddevice as sd
import msvcrt
import time


def record_audio(
    max_duration: int = 60,
    sample_rate: int = 16000,
    silence_threshold: float = 0.01,
    silence_duration: float = 2.0
) -> tuple:
    """
    Records audio with three stop conditions:
    1. Silence for silence_duration seconds
    2. max_duration seconds reached
    3. User presses Enter (Windows msvcrt)

    Returns (audio_array: np.ndarray, duration: float)
    """
    print("\n🎙️  Recording... (speak now)")
    print("    Press Enter to stop early.\n")

    frames = []
    stop_reason = "silence"

    # Track silence
    silence_counter = 0
    silence_limit = int(
        silence_duration / 0.1
    )  # checks at 100ms intervals

    start_time = time.time()

    def audio_callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype='float32',
        callback=audio_callback
    )

    with stream:
        while True:
            time.sleep(0.1)  # 100ms polling interval

            elapsed = time.time() - start_time

            # Stop condition 1 — max duration
            if elapsed >= max_duration:
                stop_reason = "timeout"
                break

            # Stop condition 2 — Enter key pressed
            # msvcrt.kbhit() is non-blocking
            # returns True if a key is waiting
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key in ('\r', '\n'):  # Enter key
                    stop_reason = "enter"
                    break

            # Stop condition 3 — silence detection
            if frames:
                recent = frames[-1].flatten()
                energy = np.sqrt(np.mean(recent ** 2))

                if energy < silence_threshold:
                    silence_counter += 1
                    if silence_counter >= silence_limit:
                        stop_reason = "silence"
                        break
                else:
                    silence_counter = 0

    # Assemble audio
    if not frames:
        return np.zeros(sample_rate, dtype='float32'), 0.0

    audio_array = np.concatenate(
        frames, axis=0
    ).flatten()
    duration = len(audio_array) / sample_rate

    # Print stop reason
    reasons = {
        "silence": "🔇  Silence detected — stopping.",
        "timeout": "⏱️  60 seconds reached — stopping.",
        "enter":   "⏹️  Stopped by Enter key."
    }
    print(reasons.get(stop_reason, "🔇  Stopped."))

    return audio_array, duration
