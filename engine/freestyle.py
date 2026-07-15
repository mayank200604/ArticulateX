"""
freestyle.py — Freestyle mode logic.

Handles open-ended freestyle prompt selection.
"""

import random
from engine.topics import FREESTYLE_TOPICS


def get_freestyle_prompt() -> tuple:
    """
    Returns (prompt_type, prompt_content)
    prompt_type is 'topic'
    """
    print("\nFreeStyle Mode")
    print("──────────────────────────────")
    topic = random.choice(FREESTYLE_TOPICS)
    print(f"\nYour topic: {topic}")
    print("Speak about this for at least 30 seconds.")
    return ("topic", topic)

