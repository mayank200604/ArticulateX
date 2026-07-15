"""
analyser.py — Speech analysis engine for ArticulateX Phase 1.

Analyses a transcript for articulation quality:
  • Filler word detection (definite + ambiguous categories)
  • Words per minute (WPM)
  • Overused content words
  • Average sentence length
  • Opening position clarity
  • Sentence count
"""

import re
from collections import Counter


# ── Definite fillers — always count every occurrence ────────────
# Expanded to catch non-standard AssemblyAI transcription forms.
DEFINITE_FILLERS = {
    "um", "uh", "mm", "hmm", "ah", "er", "erm", "eh",
    "like", "basically", "actually", "right",
    "literally", "honestly",
    "you know", "i mean", "okay so", "so basically",
    "kind of", "sort of", "i think", "i guess",
    "you see", "anyway",
}

# ── Ambiguous fillers — only count excess above 2 ──────────────
AMBIGUOUS_FILLERS = {
    "and", "so", "well", "just", "really",
    "very", "quite", "now",
}

# ── Secondary mid-sentence filler patterns ─────────────────────
# Catches fillers embedded mid-sentence without punctuation,
# common in AssemblyAI real-time transcripts.
# Each pattern is a regex matching a filler in natural context.
_MID_SENTENCE_FILLER_PATTERNS = [
    r'\b(?:and|but|so)\s+(?:like|basically|actually)\b',
    r'\b(?:i|you)\s+(?:like|basically)\b',
    r'\blike\s+(?:you know|i mean)\b',
    r'\byou\s+know\s+like\b',
    r'\bi\s+mean\s+like\b',
    r'\bright\s+so\b',
]


def _scan_mid_sentence_fillers(text: str) -> int:
    """
    Secondary scan that catches filler patterns appearing
    mid-sentence without punctuation around them.
    Returns the total additional filler hits found.
    """
    count = 0
    for pattern in _MID_SENTENCE_FILLER_PATTERNS:
        count += len(re.findall(pattern, text))
    return count

# ── Opening position indicators ────────────────────────────────
OPENING_PHRASES = [
    "i believe",
    "i think",
    "i argue",
    "my view",
    "in my opinion",
    "i would say",
    "my point is",
    "the reason",
]

# ── Common stop words excluded from "overused" detection ────────
# We only flag *content* words, not function words.
STOP_WORDS = {
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "his", "her", "its", "the", "a", "an", "and",
    "or", "but", "if", "in", "on", "at", "to", "for", "of", "with",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "shall", "should", "can", "could", "may", "might", "must",
    "that", "this", "these", "those", "what", "which", "who",
    "whom", "how", "when", "where", "why", "not", "no", "so",
    "than", "then", "just", "also", "very", "too", "as", "by",
    "from", "about", "into", "there", "here", "all", "some",
    "any", "each", "every", "both", "few", "more", "most",
    "other", "such", "only", "own", "same", "up", "out",
    "don", "t", "s", "re", "ve", "ll", "d", "m",
}


def analyse(
    transcript: str,
    duration_seconds: float,
    detected_fillers: list = None,
) -> dict:
    """
    Run full articulation analysis on a transcript.

    Parameters
    ----------
    transcript : str
        The raw transcript text from Whisper.
    duration_seconds : float
        How long the user spoke (seconds).
    detected_fillers : list, optional
        List of filler word strings extracted directly from
        AssemblyAI word-level disfluency data. When provided
        and non-empty, these are used as the primary filler
        source; regex scanning adds any extras on top.

    Returns
    -------
    results : dict
        Keys: filler_words, total_fillers, wpm, overused_words,
              avg_sentence_length, has_clear_opening_position,
              sentence_count, word_count
    """
    text_lower = transcript.lower()

    # ── 1. Filler word detection ────────────────────────────────
    filler_hits = []
    words = text_lower.split()

    if detected_fillers:
        # ── Primary source: AssemblyAI disfluency markers ───────
        # Count occurrences of each filler word from the API
        from collections import Counter as _Counter
        api_counts = _Counter(detected_fillers)
        for filler_word, count in api_counts.items():
            filler_hits.append({"word": filler_word, "count": count})

        api_total = sum(api_counts.values())

        # ── Safety net: regex scan for anything the API missed ──
        regex_total = 0
        regex_extras = []
        for filler in DEFINITE_FILLERS:
            count = len(re.findall(
                r'\b' + re.escape(filler) + r'\b',
                text_lower
            ))
            if count > 0:
                # Only count the excess above what the API already found
                api_for_this = api_counts.get(filler, 0)
                extra = max(0, count - api_for_this)
                if extra > 0:
                    regex_extras.append({"word": filler, "count": extra})
                    regex_total += extra

        for filler in AMBIGUOUS_FILLERS:
            count = words.count(filler)
            excess = max(0, count - 2)
            if excess > 0:
                regex_extras.append({"word": filler, "count": excess})
                regex_total += excess

        # Add regex extras on top of API fillers
        filler_hits.extend(regex_extras)
        total_fillers = api_total + regex_total

    else:
        # ── Fallback: regex-only scanning (no API data) ─────────
        # Definite fillers — count only whole-word occurrences.
        # Using regex word boundaries to avoid false matches where
        # filler substrings appear inside real words
        # e.g. 'er' inside 'overriding', 'ah' inside 'ahead',
        # 'um' inside 'document'.
        for filler in DEFINITE_FILLERS:
            count = len(re.findall(
                r'\b' + re.escape(filler) + r'\b',
                text_lower
            ))
            if count > 0:
                filler_hits.append({"word": filler, "count": count})

        # Ambiguous fillers — only count excess above 2
        # These are single tokens so word-split counting is fine
        for filler in AMBIGUOUS_FILLERS:
            count = words.count(filler)
            excess = max(0, count - 2)
            if excess > 0:
                filler_hits.append({"word": filler, "count": excess})

        total_fillers = sum(f["count"] for f in filler_hits)

    # Secondary scan — catch mid-sentence filler patterns that
    # the primary word-boundary pass may miss
    mid_sentence_extra = _scan_mid_sentence_fillers(text_lower)
    if mid_sentence_extra > 0:
        filler_hits.append({
            "word": "(mid-sentence pattern)", "count": mid_sentence_extra
        })
        total_fillers += mid_sentence_extra

    # ── 2. Word count and WPM ───────────────────────────────────
    word_count = len(words)
    # Guard against division by zero for very short recordings
    duration_minutes = max(duration_seconds / 60.0, 0.01)
    wpm = round(word_count / duration_minutes)

    # ── 3. Sentence splitting and stats ─────────────────────────
    sentences = _split_sentences(transcript)
    sentence_count = len(sentences)
    avg_sentence_length = round(
        word_count / max(sentence_count, 1), 1
    )

    # ── 4. Overused content words ───────────────────────────────
    overused_words = _find_overused_words(text_lower)

    # ── 5. Clear opening position ───────────────────────────────
    has_clear_opening_position = _has_opening_position(text_lower)

    return {
        "filler_words": filler_hits,
        "total_fillers": total_fillers,
        "wpm": wpm,
        "word_count": word_count,
        "overused_words": overused_words,       # list of (word, count)
        "avg_sentence_length": avg_sentence_length,
        "has_clear_opening_position": has_clear_opening_position,
        "sentence_count": sentence_count,
    }


# ── Internal helpers ────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using punctuation boundaries.
    Falls back to treating the entire text as one sentence
    if no sentence-ending punctuation is found.
    """
    # Split on . ? ! followed by a space or end-of-string
    raw = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in raw if s.strip()]
    return sentences if sentences else [text.strip()] if text.strip() else []


def _find_overused_words(text: str) -> list[tuple[str, int]]:
    """
    Find content words that appear 3 or more times.
    Returns a sorted list of (word, count) tuples.
    """
    # Tokenise to lowercase alpha words only
    tokens = re.findall(r"[a-z]+", text)
    content_words = [w for w in tokens if w not in STOP_WORDS and len(w) > 2]
    counts = Counter(content_words)
    overused = [(word, cnt) for word, cnt in counts.most_common() if cnt >= 3]
    return overused


def _has_opening_position(text: str) -> bool:
    """Check whether the speaker used any opening position phrase."""
    return any(phrase in text for phrase in OPENING_PHRASES)
