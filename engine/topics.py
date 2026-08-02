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
    "This house believes arts subjects should be removed from the mandatory school curriculum.",
    "Should artificial intelligence be allowed to make legal decisions?",
    "If given a choice between fame and impact, which would you choose?",
    "Is it ethical for companies to monitor employee productivity remotely?",
    "Should freedom of speech have limits?",
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

FREESTYLE_WORDS = [
    "Resilience",
    "Ambiguity",
    "Nostalgia",
    "Vulnerability",
    "Curiosity",
    "Authenticity",
    "Patience",
    "Serendipity",
    "Perseverance",
    "Empathy",
    "Procrastination",
    "Courage",
    "Minimalism",
    "Intuition",
    "Compromise",
    "Solitude",
    "Gratitude",
    "Adaptability",
    "Innovation",
    "Skepticism",
    "Legacy",
    "Momentum",
    "Friction",
    "Paradox",
    "Nuance"
]

FREESTYLE_SCENARIOS = [
    "Describe a moment that changed how you think about something important",
    "If you could have one conversation with anyone in history, who and why",
    "What does success mean to you personally, not to society",
    "Describe a skill you wish you had and why it matters to you",
    "If you had to teach one lesson to every 18-year-old, what would it be",
    "Pitch a completely useless invention and try to convince me to buy it",
    "Explain the concept of the internet to a time traveler from 1850",
    "Describe your perfect day from the moment you wake up to when you sleep",
    "What is the most difficult decision you've ever had to make?",
    "If you could teleport anywhere right now, where would you go and why?",
    "Argue that a hotdog is, or is not, a sandwich",
    "What is a popular opinion that you completely disagree with?",
    "If you had to eat only one meal for the rest of your life, what would it be?",
    "Describe a time when you completely failed at something, and what you learned",
    "If animals could talk, which species would be the rudest?",
    "What is the best piece of advice you have ever received?",
    "How would you survive a zombie apocalypse using only items in your room?",
    "If you were a color, what color would you be and why?",
    "Explain a complex hobby or interest of yours to a 5-year-old",
    "If you could instantly become an expert in any subject, what would you choose?",
    "Describe a book or movie that profoundly impacted your worldview",
    "What is a habit you are trying to build, and why is it so hard?",
    "If you had unlimited funding to start a charity, what would its mission be?",
    "What is the most beautiful place you have ever seen with your own eyes?",
    "If you could redesign the human body, what one change would you make?"
]

FREESTYLE_TOPICS = FREESTYLE_SCENARIOS + FREESTYLE_WORDS

# ── Backward compatibility aliases ──────────────────────────────
# These maintain the old dict/list interfaces so existing code that
# hasn't been updated yet still works without crashing.

DEBATE_TOPICS = {
    "level1": DEBATE_LEVEL_1_TOPICS,
    "level2": DEBATE_LEVEL_2_TOPICS,
    "level3": DEBATE_LEVEL_3_TOPICS,
}
