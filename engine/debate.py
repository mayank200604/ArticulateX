"""
debate.py — Debate mode orchestration.

Handles level configs, side selection,
pause detection, turn timing.
"""

import time
import threading


DEBATE_CONFIG = {
    1: {
        "interrupt_probability": 0.0,
        "pause_warning_seconds": 4,
        "pause_terminate_seconds": None,
        "filler_tolerance": 2,
        "observation_depth": "light",
        "user_picks_side": True,
        "ai_picks_topic": False,
        "nudge_message": "Take your time, keep going..."
    },
    2: {
        "interrupt_probability": 0.22,
        "pause_warning_seconds": 3,
        "pause_terminate_seconds": 5,
        "filler_tolerance": 0,
        "observation_depth": "medium",
        "user_picks_side": True,
        "ai_picks_topic": True,
        "nudge_message": "Keep going — you have a few seconds."
    },
    3: {
        "interrupt_probability": 0.50,
        "pause_warning_seconds": None,
        "pause_terminate_seconds": 2,
        "filler_tolerance": 0,
        "observation_depth": "deep",
        "user_picks_side": False,
        "ai_picks_topic": True,
        "nudge_message": None
    }
}


def get_ai_side(user_side: str) -> str:
    """Return the opposite side for the AI."""
    if user_side.lower() in ["positive", "for", "agree"]:
        return "against"
    return "for"


def assign_random_side() -> str:
    """Randomly assign a debate side."""
    import random
    return random.choice(["for", "against"])


def should_interrupt(level: int) -> bool:
    """Determine if AI should interrupt based on level probability."""
    import random
    prob = DEBATE_CONFIG[level]["interrupt_probability"]
    return random.random() < prob
