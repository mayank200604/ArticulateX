"""
confidence.py — Confidence signal tracker for ArticulateX.

Tracks hedging and uncertainty language silently.
Never interrupts. Never displays during session.
Only used in end-of-session feedback.
"""

CONFIDENCE_SIGNALS = [
    "i think",
    "i guess",
    "i'm not sure but",
    "i am not sure but",
    "maybe",
    "kind of",
    "sort of",
    "i mean",
    "you know",
    "does that make sense",
    "something like that",
    "i could be wrong but",
    "not sure",
    "perhaps",
    "possibly",
    "i suppose",
    "if that makes sense",
    "i feel like"
]


def analyse_confidence(transcript: str) -> dict:
    """
    Analyse a transcript for confidence/hedging signals.
    Returns dict with total count, individual signals, and level.
    """
    text_lower = transcript.lower()
    found_signals = []

    for signal in CONFIDENCE_SIGNALS:
        if signal in text_lower:
            count = text_lower.count(signal)
            found_signals.append({
                "signal": signal,
                "count": count,
                "quote": extract_quote_with_signal(
                    transcript, signal
                )
            })

    total_signals = sum(s["count"] for s in found_signals)

    return {
        "total_confidence_signals": total_signals,
        "signals_found": found_signals,
        "confidence_level": classify_confidence(total_signals)
    }


def extract_quote_with_signal(
    transcript: str, signal: str
) -> str:
    """Extract the sentence containing the signal."""
    sentences = transcript.replace('!', '.').replace('?', '.').split('.')
    for sentence in sentences:
        if signal in sentence.lower():
            return sentence.strip()[:100]
    return ""


def classify_confidence(total: int) -> str:
    """Classify overall confidence level from signal count."""
    if total == 0:
        return "strong"
    elif total <= 2:
        return "moderate"
    elif total <= 5:
        return "weak"
    else:
        return "very weak"
