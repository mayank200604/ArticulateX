"""
topics.py — Topic banks for all ArticulateX modes.

Contains curated topic pools for Debate (3 levels) and FreeStyle.
Each debate level list contains 25 shared topics plus 5 level-specific topics.
FreeStyle contains 5 open-ended prompts.
"""

# ── Shared topics (used across all debate levels) ────────────────

_SHARED_DEBATE_TOPICS = [
    # Easy and Relatable (1–10)
    "Should students be allowed to use phones in classrooms?",
    "Is working from home better than working from office?",
    "Do social media platforms do more good than harm?",
    "Should college attendance be made optional?",
    "Is cooking at home better than eating out?",
    "Should sports be made compulsory in school?",
    "Do video games affect students negatively?",
    "Is morning routine more important than night routine?",
    "Should pets be allowed in workplaces?",
    "Is reading books better than watching documentaries?",

    # Contextual and Opinion-Based (11–20)
    "Is financial success more important than job satisfaction?",
    "Should voting be made mandatory for all citizens?",
    "Does technology make us more productive or more distracted?",
    "Is competition healthy or does it create unnecessary pressure?",
    "Should cities prioritise public transport over private vehicles?",
    "Is entrepreneurship a better career path than employment?",
    "Does modern education prepare students for real life?",
    "Should salaries be made public within organisations?",
    "Is ambition a virtue or a source of unhappiness?",
    "Does social media create unrealistic expectations about life?",

    # Challenging and Hypothetical (21–25)
    "If you had to eliminate one subject from school permanently, what would it be and why?",
    "Should artificial intelligence be allowed to make legal decisions?",
    "If given a choice between fame and impact, which would you choose?",
    "Is it ethical for companies to monitor employee productivity remotely?",
    "Should freedom of speech have limits, and who decides those limits?",
]

# ── Level-specific topics ────────────────────────────────────────

_LEVEL_1_SPECIFIC = [
    "Is discipline more important than creativity in school?",
    "Should junk food be banned in school canteens?",
    "Is it better to have one deep friendship or many casual ones?",
    "Should higher education be free for everyone?",
    "Is failure a better teacher than success?",
]

_LEVEL_2_SPECIFIC = [
    "Does globalisation benefit developing countries more than developed ones?",
    "Is democracy the most effective form of government?",
    "Should the retirement age be increased given longer life expectancy?",
    "Does the media have a responsibility to shape public opinion?",
    "Is economic growth compatible with environmental sustainability?",
]

_LEVEL_3_SPECIFIC = [
    "Should artificial intelligence replace human teachers in classrooms?",
    "Is privacy a luxury that modern society can no longer afford?",
    "Does capitalism inherently create inequality or is it the best system available?",
    "Should gene editing in humans be legalised for disease prevention?",
    "Is nationalism a strength or a threat to global progress?",
]

# ── Combined debate topic lists (25 shared + 5 level-specific) ──

DEBATE_LEVEL_1_TOPICS = _SHARED_DEBATE_TOPICS + _LEVEL_1_SPECIFIC
DEBATE_LEVEL_2_TOPICS = _SHARED_DEBATE_TOPICS + _LEVEL_2_SPECIFIC
DEBATE_LEVEL_3_TOPICS = _SHARED_DEBATE_TOPICS + _LEVEL_3_SPECIFIC

# ── FreeStyle topics (open-ended, no right answer) ───────────────

FREESTYLE_TOPICS = [
    "Describe a moment that changed how you think about something important",
    "If you could have one conversation with anyone in history, who and why",
    "What does success mean to you personally, not to society",
    "Describe a skill you wish you had and why it matters to you",
    "If you had to teach one lesson to every 18-year-old, what would it be",
]

# ── Backward compatibility aliases ──────────────────────────────
# These maintain the old dict/list interfaces so existing code that
# hasn't been updated yet still works without crashing.

DEBATE_TOPICS = {
    "level1": DEBATE_LEVEL_1_TOPICS,
    "level2": DEBATE_LEVEL_2_TOPICS,
    "level3": DEBATE_LEVEL_3_TOPICS,
}

FREESTYLE_WORDS = FREESTYLE_TOPICS
FREESTYLE_SCENARIOS = FREESTYLE_TOPICS
