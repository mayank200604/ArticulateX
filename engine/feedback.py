"""
feedback.py — Brutal end-of-session report generator.

Reads full session data, sends to LLM with structured prompt,
returns specific honest feedback. No sugar-coating.
"""

from llm import call_llm
from core.memory import get_session
import json

# ── Acknowledged-struggle sentence (inserted only when metrics
#    are genuinely worse than the user's personal baseline) ───────
STRUGGLE_SENTENCE = (
    "This was a harder session than your usual standard. "
    "That is not a setback — difficulty spikes consistently "
    "precede measurable improvement in communication training."
)

FEEDBACK_PROMPT = """
You are writing a candid debrief as if you are a hiring manager, 
senior colleague, or interviewer who just watched this person 
speak in a live setting.

Your role is NOT to score them like an app. Your role is to tell 
them exactly what a real professional listener would have noticed, 
thought, and silently judged during this session. Every observation 
you make should sound like it is coming from someone who has sat 
across a table from hundreds of candidates and colleagues — someone 
who knows exactly what separates people who communicate well from 
people who do not.

ArticulateX is a COMMUNICATION coaching platform. 
Not a debate competition. Not a knowledge test.

THE 70/30 RULE YOU FOLLOW IN ALL FEEDBACK:

70% -- COMMUNICATION QUALITY (always dominant):
- Fluency: did they speak without filler bursts 
  or unnatural pauses?
- Confidence: did they sound like they believed 
  what they were saying?
- Continuity: did they finish their thoughts?
- Clarity of delivery: could the listener follow?
- Structure: did they have a clear position 
  and maintain it?
- Composure: did they stay calm under pressure?
- Holding position: did they back down too easily?

30% -- CONTENT RELEVANCE (supporting role):
- Did they stay on topic?
- Did they make an identifiable claim?
- At higher levels -- did their claim become more 
  specific and precise across turns?

WHAT YOU NEVER EVALUATE:
- Factual accuracy of their argument
- Whether they had strong evidence
- Whether experts would agree with them
- Whether their examples are accurate or real
- Intellectual depth or sophistication of the point

{struggle_preamble}SESSION DATA:
Mode: {mode}
Topic: {topic}
Total turns: {total_turns}
Average WPM: {avg_wpm}
Average filler count per turn: {avg_fillers}

FULL CONVERSATION:
{full_conversation}

CONFIDENCE SIGNALS DETECTED:
{confidence_summary}

TURN-BY-TURN METRICS:
{turn_details}

{level_feedback_tone}

Write your feedback in EXACTLY this structure.
No extra sections. No reordering.
Write every section as if you are the professional observer 
describing what they noticed — not an app displaying a score.

OVERALL VERDICT
One honest sentence. As a senior professional who just watched 
this person speak, what is your immediate read on them as a 
communicator — based on HOW they spoke, not on the strength 
of their argument.

WHAT WORKED
Maximum 2 things that a hiring manager or senior colleague 
would have genuinely noticed as strengths in their 
COMMUNICATION -- not their content.
Each must include an exact quote from their words.
If nothing genuinely worked, say so honestly — a real 
interviewer would have noticed that too.

THE MAIN PROBLEM
The single biggest COMMUNICATION issue that a professional 
listener would have flagged. Quote the exact words that 
show it. This must be about HOW they spoke -- delivery, 
confidence, structure, fluency -- not about 
content quality.
MANDATORY: You MUST write at least two full sentences for 
this section regardless of session length or filler count. 
Even if the session was clean with few fillers, there is 
always something that could have been stronger — structure, 
conviction, evidence use, or clarity of delivery. A dash, 
a single word, or an empty section is NEVER acceptable. 
Always provide a substantive observation.

THE PATTERN
Something in their COMMUNICATION behaviour that a senior 
colleague would have noticed repeating across at least 
2-3 turns.
Quote specific turn numbers.
Quote their exact words.
Explain what this pattern costs them in a real professional 
setting — a meeting, an interview, a presentation.
This must be observable behaviour -- not opinion 
about their argument quality.
MANDATORY: You MUST write at least two full sentences for 
this section regardless of session length or filler count. 
Even if no negative pattern exists, identify a structural 
or delivery pattern — such as always opening the same way, 
not varying sentence length, or not using pauses 
effectively. A dash, a single word, or an empty section 
is NEVER acceptable. Always provide a substantive 
observation.

CONFIDENCE REPORT
Total hedging signals found.
Top 2 most frequent signals.
The single worst moment -- exact quote from transcript.
What this specific quote signals to a real listener 
sitting across the table.
If zero signals: "No hedging signals. Delivery was direct."

THREE THINGS TO FIX
Minimum 2 out of 3 fixes must be COMMUNICATION fixes.
Maximum 1 fix can be a content relevance fix -- 
and even that must be framed as a precision issue, 
not a knowledge gap.
Frame each fix as what a senior professional would 
advise after observing this session.

Each fix follows this exact four-part structure:
POINT: The specific communication problem -- one sentence.
REASON: Why a professional listener would hold this against 
them -- one sentence.
EXAMPLE: Exact quote from their transcript showing this.
TRY THIS INSTEAD: A stronger version of that exact 
moment showing better communication -- not more knowledge.

BANNED IN THREE THINGS TO FIX:
- "You should have provided evidence"
- "Your argument needed stronger examples"
- "The point was not convincing"
- Any invented statistics or percentages
- Any invented study or research reference
- Any fix that is purely about content strength

ONE EARNED ENCOURAGEMENT
One specific moment that a hiring manager would have 
genuinely noted as a sign of communication potential.
Must be real -- not invented to be kind.
Must reference exact words from transcript.
CRITICAL: If there is no genuinely earned moment, DO NOT 
include this section at all. DO NOT print the header 
"ONE EARNED ENCOURAGEMENT". DO NOT print any placeholder 
text. The following phrases are BANNED:
- "No standout moment this session"
- "Nothing stood out"
- "No earned encouragement"
- Any sentence explaining why the section is absent
If nothing genuinely stands out, skip this section 
entirely — do not output the header or any content 
for it. Proceed directly to SPOKEN SUMMARY.

SPOKEN SUMMARY
3-4 sentences spoken aloud to the user, as if the 
professional observer is giving them a final word 
before they leave the room.
Must contain:
- The single most important communication problem
- The single most actionable fix
- One forward-looking sentence
Maximum 60 words. Plain spoken language.
No bullet points. No headers.
"""


def generate_session_feedback(
    session_id: int,
    session_turns: list,
    mode: str,
    topic: str,
    confidence_data: list,
    level: int = 0,
    user_profile: dict = None
) -> str:
    """
    Generate the brutal end-of-session feedback report.

    Parameters
    ----------
    session_id : int
        The current session ID.
    session_turns : list
        List of turn data dicts from the session.
    mode : str
        Mode name (e.g. "Debate Level 1", "FreeStyle").
    topic : str
        The topic or prompt used in the session.
    confidence_data : list
        List of confidence analysis dicts, one per turn.
    user_profile : dict, optional
        Historical profile from get_user_profile().
        Used to detect acknowledged-struggle condition.

    Returns
    -------
    str
        The formatted feedback report from the LLM.
    """
    if not session_turns:
        return "No turns recorded in this session."

    # Build full conversation text
    full_conversation = "\n".join([
        f"Turn {t['turn_number']} (User): {t['transcript']}"
        for t in session_turns
    ])

    # Build confidence summary
    all_signals = {}
    for turn_conf in confidence_data:
        for signal in turn_conf.get("signals_found", []):
            word = signal["signal"]
            if word in all_signals:
                all_signals[word] += signal["count"]
            else:
                all_signals[word] = signal["count"]

    total_confidence_signals = sum(all_signals.values())
    confidence_summary = (
        f"Total hedging signals: {total_confidence_signals}\n"
        f"Breakdown: {json.dumps(all_signals, indent=2)}"
        if all_signals else "No hedging signals detected."
    )

    # Build turn details
    turn_details = "\n".join([
        f"Turn {t['turn_number']}: "
        f"WPM={t['wpm']}, "
        f"Fillers={t['filler_count']}, "
        f"Clear position={'Yes' if t['held_position'] else 'No'}, "
        f"Used evidence={'Yes' if t['used_evidence'] else 'No'}, "
        f"Asked question={'Yes' if t['asked_question'] else 'No'}"
        for t in session_turns
    ])

    avg_wpm = sum(t["wpm"] for t in session_turns) / len(session_turns)
    avg_fillers = sum(
        t["filler_count"] for t in session_turns
    ) / len(session_turns)

    if level == 1:
        level_feedback_tone = """
LEVEL 1 FEEDBACK RULES:
Harshness: 3 out of 10.
This person is building confidence. Be honest 
but never crushing.

OVERALL VERDICT: Must acknowledge effort and 
identify one main thing to work on.
Never start with "hesitant and unclear."

WHAT WORKED: Find at least 1-2 genuine 
communication positives. Even small things count.

THREE THINGS TO FIX: Simple and achievable. 
All communication-based. Never about content strength.

ONE EARNED ENCOURAGEMENT: Mandatory. 
Must be specific and real.

BANNED IN LEVEL 1 FEEDBACK:
"hesitant and unclear communicator"
"struggles to convey"
"lacks conviction"
Any language implying fundamental failure.
"""

    elif level == 2:
        level_feedback_tone = """
LEVEL 2 FEEDBACK RULES:
Harshness: 6 out of 10.
Honest and direct. No softening. No cruelty.

OVERALL VERDICT: Honest assessment of their 
current communication level. Not encouraging, 
not crushing. Factual.

WHAT WORKED: Only if genuinely good. 
Be selective.

THREE THINGS TO FIX: More demanding than Level 1. 
At least one fix about structure or holding position.

ONE EARNED ENCOURAGEMENT: Only if deserved.
Skip if performance was average throughout.
"""

    elif level == 3:
        level_feedback_tone = """
LEVEL 3 FEEDBACK RULES:
Harshness: 10 out of 10.
Zero softening. This person chose the hardest mode.
Treat them like a professional under evaluation.

OVERALL VERDICT: Reflect Level 3 standards. 
A mediocre performance is a mediocre performance. 
Say it directly. Never soften with "showed potential."

WHAT WORKED: Only if genuinely strong.
If nothing was genuinely strong write:
"Nothing in this session stood out at Level 3 
standards."

THREE THINGS TO FIX: Demanding and specific.
Quote exact turn numbers and exact words.
At least one fix about confidence under pressure.

ONE EARNED ENCOURAGEMENT: Only if performance 
was objectively strong in at least one area.
If not -- omit this section entirely from the report.
Do not print any placeholder sentence.

BANNED IN LEVEL 3 FEEDBACK:
"showed potential"
"willingness to engage"
"good attempt"
Any verdict that could apply to Level 1.
"""

    elif "freestyle" in mode.lower() or "weird" in mode.lower():
        level_feedback_tone = """
FREESTYLE / WEIRD SITUATION FEEDBACK RULES:
Harshness: 2 out of 10.
This was relaxed speaking practice.

OVERALL VERDICT: Positive or neutral only.

WHAT WORKED: Find at least 2 genuine things.

THREE THINGS TO FIX: Simple, kind, achievable.
Focus on fluency and flow only.
Never mention content quality or argument strength.

ONE EARNED ENCOURAGEMENT: Mandatory.
"""

    else:
        level_feedback_tone = ""

    # ── Acknowledged-struggle detection ───────────────────────────
    # Compare current session metrics against the user's historical
    # baseline.  Insert the struggle sentence ONLY when performance
    # is genuinely worse than personal baseline.
    struggle_preamble = ""
    if user_profile and user_profile.get("total_sessions", 0) > 0:
        hist_wpm = user_profile.get("avg_wpm", 0)
        hist_fillers = user_profile.get("avg_fillers", 0)

        wpm_struggling = (
            hist_wpm > 0
            and avg_wpm < hist_wpm * 0.80
        )
        filler_struggling = (
            hist_fillers > 0
            and avg_fillers > hist_fillers * 1.50
        )

        if wpm_struggling or filler_struggling:
            struggle_preamble = (
                "IMPORTANT — INSERT THIS EXACT SENTENCE AT THE "
                "VERY BEGINNING OF YOUR REPORT, BEFORE THE "
                "OVERALL VERDICT, ON ITS OWN LINE:\n"
                f'"{STRUGGLE_SENTENCE}"\n\n'
            )

    prompt = FEEDBACK_PROMPT.format(
        mode=mode,
        topic=topic,
        total_turns=len(session_turns),
        avg_wpm=round(avg_wpm, 1),
        avg_fillers=round(avg_fillers, 1),
        full_conversation=full_conversation,
        confidence_summary=confidence_summary,
        turn_details=turn_details,
        level_feedback_tone=level_feedback_tone,
        struggle_preamble=struggle_preamble
    )

    return call_llm(
        prompt,
        temperature=0.2,
        max_tokens=900
    )
