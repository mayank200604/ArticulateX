"""
utils.py — Shared helpers for ArticulateX Phase 1.

Provides microphone recording with automatic silence detection,
Enter-key termination, and timing utilities.
"""

import numpy as np


def is_audio_valid(
    audio_array,
    sample_rate: int = 16000,
    min_duration: float = 1.5,
    min_energy: float = 0.002
) -> tuple:
    """
    Returns (is_valid: bool, reason: str)
    Checks if audio contains real speech before
    sending to Whisper.
    """
    # Check duration
    duration = len(audio_array) / sample_rate
    if duration < min_duration:
        return False, "too_short"

    # Check energy — silence and noise have very
    # low RMS energy
    rms = np.sqrt(np.mean(audio_array ** 2))
    if rms < min_energy:
        return False, "too_quiet"

    # Check if audio has variation — pure noise
    # has very low standard deviation relative
    # to its mean
    std = np.std(audio_array)
    if std < 0.005:
        return False, "no_variation"

    return True, "valid"
