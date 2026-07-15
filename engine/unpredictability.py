"""
unpredictability.py — Strategy picker for debate mode.

10 strategies. Never repeats last 3.
Overrides based on user weakness detection.
"""

import random
from enum import Enum


class Strategy(Enum):
    AGREE_THEN_CHALLENGE = "agree_then_challenge"
    DEMAND_ONE_SENTENCE = "demand_one_sentence"
    DEVILS_ADVOCATE = "devils_advocate"
    ASK_FOR_EVIDENCE = "ask_for_evidence"
    PUSH_BACK_HARD = "push_back_hard"
    INTERRUPT_REDIRECT = "interrupt_redirect"
    CHANGE_TOPIC = "change_topic"
    MISUNDERSTAND = "misunderstand"
    ASK_TO_REPEAT = "ask_to_repeat"
    SHARP_FOLLOWUP = "sharp_followup"


STRATEGY_WEIGHTS = [
    (Strategy.AGREE_THEN_CHALLENGE, 15),
    (Strategy.DEMAND_ONE_SENTENCE, 3),
    (Strategy.DEVILS_ADVOCATE, 18),
    (Strategy.ASK_FOR_EVIDENCE, 15),
    (Strategy.PUSH_BACK_HARD, 12),
    (Strategy.INTERRUPT_REDIRECT, 8),
    (Strategy.CHANGE_TOPIC, 5),
    (Strategy.MISUNDERSTAND, 8),
    (Strategy.ASK_TO_REPEAT, 7),
    (Strategy.SHARP_FOLLOWUP, 10),
]

STRATEGY_INSTRUCTIONS = {
    Strategy.AGREE_THEN_CHALLENGE:
        "Acknowledge one thing they said that "
        "makes sense. Then challenge the main "
        "claim from a completely different angle "
        "they have not considered. Keep both "
        "parts in plain simple language. "
        "No demands for statistics.",

    Strategy.DEMAND_ONE_SENTENCE:
        "Do not respond to their content. Say: "
        "'Stop. Tell me your main point in one sentence only.' "
        "Wait for them to do it.",

    Strategy.DEVILS_ADVOCATE:
        "Take the complete opposite position and "
        "defend it in plain simple language. "
        "No jargon. No demands for data. "
        "Just argue the other side confidently "
        "and let them respond to your point.",

    Strategy.ASK_FOR_EVIDENCE:
        "Challenge them to justify their position "
        "more deeply. Ask WHY they believe what "
        "they said, not for statistics or studies. "
        "Use questions like 'Why do you think that "
        "is true?' or 'What makes you so confident "
        "about that?' or 'Most people would push "
        "back on that — why are you right?' "
        "Never ask for data, research, or "
        "specific named examples.",

    Strategy.PUSH_BACK_HARD:
        "Disagree strongly with their main point. "
        "Find one specific thing they said that "
        "does not add up and challenge it directly. "
        "Do not ask for data or examples. "
        "Instead argue the opposite position "
        "with conviction. Make them defend "
        "their actual words.",

    Strategy.INTERRUPT_REDIRECT:
        "You are interrupting the user mid-point. "
        "Choose ONE of these interrupt openers randomly "
        "and use it to start your response — pick a "
        "different one each time, never repeat the same "
        "one twice in a row: "
        "Wait — / Stop there — / Actually — / "
        "Hold on — / Before you continue — / "
        "That is not right — / One moment — / "
        "Let me stop you there — / "
        "I have to cut in here — "
        "After the opener, challenge the specific point "
        "they just made directly. "
        "Maximum 2 sentences total. "
        "Do not ask for data or examples. "
        "Challenge the argument itself.",

    Strategy.CHANGE_TOPIC:
        "You are going to deliberately shift the "
        "debate to a related but different dimension "
        "of the topic that the user has not raised. "
        "Do this in exactly two sentences: "
        "Sentence 1 — Briefly dismiss or set aside "
        "their current point. Example: "
        "'That point has some merit but it misses "
        "the bigger issue entirely.' "
        "Sentence 2 — Introduce the new angle "
        "as a sharp question or statement. "
        "The pivot must be directly related to the "
        "debate topic, be something the user has NOT "
        "raised yet, force them to think and respond "
        "to something completely new, never ask for "
        "data or statistics, and sound like a real "
        "debater shifting ground not a teacher "
        "changing lesson.",

    Strategy.MISUNDERSTAND:
        "Respond to a slightly wrong interpretation of "
        "what they said. This forces them to restate their "
        "argument more clearly.",

    Strategy.ASK_TO_REPEAT:
        "Tell them you followed the words but not the point. "
        "Say something like: 'I heard you but I am not sure "
        "what you are actually arguing. Can you restate it "
        "more clearly?'",

    Strategy.SHARP_FOLLOWUP:
        "Pick one specific word or phrase they "
        "used and interrogate it directly. "
        "Example: if they said 'religion causes "
        "division' ask 'What exactly do you mean "
        "by division — and does that apply to "
        "all religion or just some?' "
        "Force them to be more precise about "
        "something they already said. "
        "Never introduce a new topic."
}


def pick_strategy(
    recent_strategies: list,
    analysis: dict,
    level: int,
    turn_number: int = 1,
    topic_change_fired: bool = False,
    just_did_redo: bool = False
) -> Strategy:
    """
    Pick the next debate strategy based on:
    - Recent strategy history (no repeats of last 3)
    - User weakness detection (override triggers)
    - Debate level (level 1 uses safe subset only)
    - Turn number (gentle start + peaceful conclusion for level 1)
    - topic_change_fired: whether CHANGE_TOPIC already executed
    - just_did_redo: whether user just did a say-it-again redo
    """
    recent = set(recent_strategies[-3:])

    # HARD BLOCK 1 — Never use DEMAND_ONE_SENTENCE or ASK_TO_REPEAT
    # on Turn 1 regardless of level — user is just opening their argument
    if turn_number == 1:
        recent = recent | {
            Strategy.DEMAND_ONE_SENTENCE,
            Strategy.ASK_TO_REPEAT
        }

    # HARD BLOCK 2 — Never use DEMAND_ONE_SENTENCE or ASK_TO_REPEAT
    # if user spoke 30+ words. They clearly made a point.
    # Do not ask them to restate or shrink it.
    word_count = analysis.get("word_count", 0)
    if word_count >= 30:
        recent = recent | {
            Strategy.DEMAND_ONE_SENTENCE,
            Strategy.ASK_TO_REPEAT
        }

    # After a redo, ban DEMAND_ONE_SENTENCE and ASK_TO_REPEAT
    # to avoid immediately asking them to restate after they retried
    if just_did_redo:
        recent = recent | {
            Strategy.DEMAND_ONE_SENTENCE,
            Strategy.ASK_TO_REPEAT
        }

    # Override logic based on user weakness
    if analysis["total_fillers"] > 4:
        if Strategy.DEMAND_ONE_SENTENCE not in recent:
            return Strategy.DEMAND_ONE_SENTENCE

    if not analysis["has_clear_opening_position"]:
        if Strategy.PUSH_BACK_HARD not in recent:
            return Strategy.PUSH_BACK_HARD

    if analysis["wpm"] > 185:
        if Strategy.MISUNDERSTAND not in recent:
            return Strategy.MISUNDERSTAND

    if level == 1:
        # Strategies completely banned in Level 1
        banned_level1 = {
            Strategy.DEMAND_ONE_SENTENCE,
            Strategy.PUSH_BACK_HARD,
            Strategy.INTERRUPT_REDIRECT,
            Strategy.CHANGE_TOPIC,
            Strategy.MISUNDERSTAND
        }

        # Additional ban for first 2 turns — keep it gentle
        if turn_number <= 2:
            banned_level1.update({
                Strategy.DEVILS_ADVOCATE,
                Strategy.ASK_FOR_EVIDENCE
            })

        # Additional ban for conclusion turns (8+)
        # Let user wrap up without being challenged
        if turn_number >= 8:
            banned_level1.update({
                Strategy.DEVILS_ADVOCATE,
                Strategy.ASK_FOR_EVIDENCE,
                Strategy.SHARP_FOLLOWUP
            })

        safe_strategies = [
            s for s, w in STRATEGY_WEIGHTS
            if s not in banned_level1 and s not in recent
        ]
        if safe_strategies:
            return random.choice(safe_strategies)
        # Fallback if all safe strategies were recently used
        fallback = [
            s for s, w in STRATEGY_WEIGHTS
            if s not in banned_level1
        ]
        return random.choice(fallback) if fallback else Strategy.SHARP_FOLLOWUP

    if level == 2:
        banned_level2 = set()
        # Never use DEMAND_ONE_SENTENCE in first 2 turns
        if turn_number <= 2:
            banned_level2.add(Strategy.DEMAND_ONE_SENTENCE)
        # Never repeat DEMAND_ONE_SENTENCE within 5 turns
        if Strategy.DEMAND_ONE_SENTENCE in set(recent_strategies[-5:]):
            banned_level2.add(Strategy.DEMAND_ONE_SENTENCE)

        available = [
            (s, w) for s, w in STRATEGY_WEIGHTS
            if s not in banned_level2 and s not in recent
        ]
        if available:
            strategies, weights = zip(*available)
            return random.choices(
                strategies, weights=weights, k=1
            )[0]

    if level == 3:
        banned_level3 = set()
        # Never repeat DEMAND_ONE_SENTENCE within 3 turns
        if Strategy.DEMAND_ONE_SENTENCE in set(recent_strategies[-3:]):
            banned_level3.add(Strategy.DEMAND_ONE_SENTENCE)
        # Never use in turn 1
        if turn_number == 1:
            banned_level3.add(Strategy.DEMAND_ONE_SENTENCE)

        # Guarantee topic change fires exactly once
        # in Level 3 sessions longer than 2 turns
        if (turn_number == 3 and
            not topic_change_fired):
            return Strategy.CHANGE_TOPIC

        # Use Level 3 specific weights
        # CHANGE_TOPIC gets boosted weight in Level 3
        level3_weights = [
            (Strategy.AGREE_THEN_CHALLENGE, 12),
            (Strategy.DEMAND_ONE_SENTENCE, 3),
            (Strategy.DEVILS_ADVOCATE, 15),
            (Strategy.ASK_FOR_EVIDENCE, 12),
            (Strategy.PUSH_BACK_HARD, 13),
            (Strategy.INTERRUPT_REDIRECT, 10),
            (Strategy.CHANGE_TOPIC, 15),  # boosted from 5
            (Strategy.MISUNDERSTAND, 8),
            (Strategy.ASK_TO_REPEAT, 5),
            (Strategy.SHARP_FOLLOWUP, 10),
        ]
        available = [
            (s, w) for s, w in level3_weights
            if s not in banned_level3 and s not in recent
        ]
        if not available:
            available = level3_weights
        strategies, weights = zip(*available)
        return random.choices(
            strategies, weights=weights, k=1
        )[0]

    # Fallback — full strategy pool
    available = [
        (s, w) for s, w in STRATEGY_WEIGHTS
        if s not in recent
    ]
    if not available:
        available = STRATEGY_WEIGHTS
    strategies, weights = zip(*available)
    return random.choices(strategies, weights=weights, k=1)[0]
