"""
weird_situation.py — Weird situation mode logic.

Picks a random image from images/ folder.
Falls back to text descriptions when folder is empty.
"""

import random
import os

IMAGES_FOLDER = "images"

# Fallback descriptions when images folder is empty
FALLBACK_DESCRIPTIONS = [
    "A cat sitting on top of a running washing machine "
    "looking completely unbothered",
    "A man in a full business suit swimming in a public fountain",
    "A shopping cart somehow parked on top of a car roof",
    "A dog sitting at a restaurant table looking at a menu",
    "A person sleeping on a luggage conveyor belt at an airport",
    "Three penguins standing in a queue at an ATM machine",
    "A cow standing inside a bus looking out the window",
    "A man ironing his clothes on a surfboard in the ocean"
]


def get_weird_situation() -> tuple:
    """
    Returns (display_type, content, description)
    display_type: 'image' or 'text'
    content: file path or situation text
    description: what to send to the LLM
    """
    # Check if images folder has content
    image_files = []
    if os.path.exists(IMAGES_FOLDER):
        image_files = [
            f for f in os.listdir(IMAGES_FOLDER)
            if f.lower().endswith(
                ('.png', '.jpg', '.jpeg', '.gif', '.webp')
            )
        ]

    if image_files:
        chosen = random.choice(image_files)
        image_path = os.path.join(IMAGES_FOLDER, chosen)
        description = f"Image file: {chosen}"
        return ("image", image_path, description)
    else:
        # Use text fallback descriptions
        description = random.choice(FALLBACK_DESCRIPTIONS)
        return ("text", description, description)


def display_situation(display_type: str, content: str) -> None:
    """Display the situation to the user."""
    if display_type == "image":
        print(f"\n🖼  Open this image to see your situation:")
        print(f"   {os.path.abspath(content)}\n")
    else:
        print(f"\n📍 Your weird situation:")
        print(f'   "{content}"\n')
