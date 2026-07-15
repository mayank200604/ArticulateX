"""
main.py — Central orchestrator for ArticulateX Phase 2.

Handles mode selection, session loops for all three modes
(Debate, FreeStyle, Weird Situation), and end-of-session
feedback generation.
"""

import os
import time
import random
from dotenv import load_dotenv

from stt import transcribe
from tts import speak
from analyser import analyse
from memory import (
    init_db, create_session, save_turn,
    update_session_stats, check_database_status
)
from confidence import analyse_confidence
from conversation import (
    get_debate_response,
    get_freestyle_response,
    get_weird_situation_response
)
from unpredictability import (
    pick_strategy, STRATEGY_INSTRUCTIONS, Strategy
)
from feedback import generate_session_feedback
from debate import (
    DEBATE_CONFIG, get_ai_side,
    assign_random_side
)
from freestyle import get_freestyle_prompt
from weird_situation import get_weird_situation, display_situation
from topics import (DEBATE_LEVEL_1_TOPICS, DEBATE_LEVEL_2_TOPICS,
    DEBATE_LEVEL_3_TOPICS)
from utils import record_audio, is_audio_valid

load_dotenv()


BANNER = r"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║        █████  ██████  ████████ ██  ██████ ██    ██           ║
║       ██   ██ ██   ██    ██    ██ ██      ██    ██           ║
║       ███████ ██████     ██    ██ ██      ██    ██           ║
║       ██   ██ ██   ██    ██    ██ ██      ██    ██           ║
║       ██   ██ ██   ██    ██    ██  ██████  ██████            ║
║                                                              ║
║            ██       █████  ████████ ███████ ██   ██          ║
║            ██      ██   ██    ██    ██       ██ ██           ║
║            ██      ███████    ██    █████     ███            ║
║            ██      ██   ██    ██    ██       ██ ██           ║
║            ███████ ██   ██    ██    ███████ ██   ██          ║
║                                                              ║
║                       ██   ██                                ║
║                        ██ ██                                 ║
║                         ███                                  ║
║                        ██ ██                                 ║
║                       ██   ██                                ║
║                                                              ║
║         AI-Powered Spoken English Communication Coach        ║
║                    Phase 2 — AI Brain Active                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


def select_mode() -> str:
    """Returns mode string based on user choice."""
    print("\nSelect Mode:")
    print("─────────────────────────────")
    print("1. FreeStyle")
    print("2. Debate — Level 1 (Easy)")
    print("3. Debate — Level 2 (Medium)")
    print("4. Debate — Level 3 (Hard)")
    print("5. Weird Situation")
    print("─────────────────────────────")
    choice = input("Enter choice (1-5): ").strip()

    mode_map = {
        "1": "freestyle",
        "2": "debate_1",
        "3": "debate_2",
        "4": "debate_3",
        "5": "weird_situation"
    }
    return mode_map.get(choice, "freestyle")


# ═════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════

def clean_transcript(text: str) -> str:
    """Remove trailing noise fragments from transcript."""
    import re
    text = text.strip()

    # Remove trailing "oh", "ah", "um", "thank you"
    # if they appear alone at the very end after a full stop
    text = re.sub(
        r'[.!?]\s+(oh|ah|um|uh|okay|thank you|thanks)\s*$',
        '.',
        text,
        flags=re.IGNORECASE
    )

    # Remove trailing fragments under 3 words
    # after the last full sentence
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) > 1:
        last = sentences[-1].strip()
        if len(last.split()) <= 2 and last[-1:] not in '.!?':
            sentences = sentences[:-1]

    return ' '.join(sentences).strip()


# ═════════════════════════════════════════════════════════════════
#  DEBATE MODE
# ═════════════════════════════════════════════════════════════════

def check_argument_clarity(
    transcript: str,
    turn_number: int
) -> bool:
    """
    Uses LLM to judge whether the user made a clear
    argument. Returns True if clear, False if not.
    Only called in Level 3 after turn 2.
    """
    from llm import call_llm

    prompt = f"""
    Read this spoken argument and answer ONE question only.

    Argument: "{transcript}"

    Did this person make a clear point or argument,
    even if brief or imperfect?

    Answer only YES or NO. Nothing else.

    YES means: there is a recognisable claim, position,
    example, or evidence — even if not perfectly worded.

    NO means: completely vague, off topic, only filler
    words, no recognisable argument at all.
    """

    result = call_llm(prompt, temperature=0.0, max_tokens=5)
    return "YES" in result.upper()


def generate_report_and_summary(
    session_id, session_turns, mode_name, topic,
    confidence_data, level=0
):
    """
    Generate full report and a short spoken summary.
    Returns (full_report, spoken_summary).
    """
    from llm import call_llm

    full_report = generate_session_feedback(
        session_id, session_turns,
        mode_name, topic,
        confidence_data,
        level=level
    )

    # Generate a concise spoken summary (3-4 sentences)
    summary_prompt = f"""
    Read this session feedback report and create a 
    spoken summary in exactly 3-4 sentences.

    REPORT:
    {full_report}

    RULES:
    - Maximum 4 sentences
    - Hit the main verdict, biggest problem, 
      and one thing to fix
    - Speak naturally as if talking to the person
    - No bullet points or formatting
    - Under 50 words total
    """

    spoken_summary = call_llm(
        summary_prompt, temperature=0.3, max_tokens=100
    )

    return full_report, spoken_summary


def run_debate(level: int):
    """Run a full debate session at the given level (1, 2, or 3)."""
    config = DEBATE_CONFIG[level]
    _LEVEL_TOPICS = {
        1: DEBATE_LEVEL_1_TOPICS,
        2: DEBATE_LEVEL_2_TOPICS,
        3: DEBATE_LEVEL_3_TOPICS,
    }
    topics = _LEVEL_TOPICS[level]

    # ── Topic selection ──────────────────────────────────────────
    if config["ai_picks_topic"]:
        topic = random.choice(topics)
        print(f"\n📌 Topic: {topic}")
    else:
        sampled = random.sample(topics, min(5, len(topics)))
        print("\nChoose your topic:")
        for i, t in enumerate(sampled, 1):
            print(f"{i}. {t}")
        idx = int(input("Select (1-5): ").strip()) - 1
        topic = sampled[max(0, min(idx, len(sampled) - 1))]
        print(f"\n📌 Topic: {topic}")

    # ── Side selection ───────────────────────────────────────────
    if config["user_picks_side"]:
        print("\nWhich side will you argue?")
        print("1. For (Positive)")
        print("2. Against (Negative)")
        side_choice = input("Select (1 or 2): ").strip()
        user_side = "for" if side_choice == "1" else "against"
    else:
        user_side = assign_random_side()
        print(f"\n🎲 You have been randomly assigned: "
              f"{user_side.upper()}")

    ai_side = get_ai_side(user_side)
    print(f"\nYou argue: {user_side.upper()}")
    print(f"AI argues: {ai_side.upper()}")
    print(f"\nMax turn time: 60 seconds")
    print("Type 'report' at any time for feedback.")
    print("Type 'quit' to end session.")
    input("\nPress Enter when ready to start...")

    # ── Session setup ────────────────────────────────────────────
    session_id = create_session(
        mode=f"debate_level_{level}",
        topic=topic
    )

    history = []
    session_turns = []
    confidence_data = []
    recent_strategies = []
    turn_number = 0
    report_already_generated = False
    final_full_report = ""
    final_spoken_summary = ""
    topic_change_fired = False

    while True:
        turn_number += 1
        # Get user input BEFORE recording starts
        print(f"\n─── Turn {turn_number} ───")
        pre_input = input(
            "Press Enter to speak, or type 'quit'/'report': "
        ).strip().lower()

        if pre_input == "quit":
            break

        if pre_input == "report":
            if session_turns:
                print("\n⏳ Generating your feedback...\n")
                final_full_report, final_spoken_summary = (
                    generate_report_and_summary(
                        session_id, session_turns,
                        f"Debate Level {level}", topic,
                        confidence_data, level=level
                    )
                )
                report_already_generated = True
            break

        # Only reach here if user pressed Enter with no text

        # ── Record and transcribe ────────────────────────────────
        silence_seconds = {1: 4.0, 2: 3.0, 3: 2.0}[level]
        audio_array, duration = record_audio(
            max_duration=60,
            silence_duration=silence_seconds
        )

        # Validate audio before sending to Whisper
        valid, reason = is_audio_valid(audio_array)
        if not valid:
            if reason == "too_quiet":
                print("⚠  No speech detected. "
                      "Please speak clearly into the microphone.")
            elif reason == "too_short":
                print("⚠  Too short. Please speak for "
                      "at least 2 seconds.")
            else:
                print("⚠  Could not detect speech. Try again.")
            continue

        print("⏳ Transcribing...")
        transcript = clean_transcript(transcribe(audio_array))

        if not transcript or not transcript.strip():
            print("⚠  Nothing detected. Try again.")
            continue

        print(f"\nYou said: {transcript}\n")

        # ── Reject turns that are too short to be meaningful ─────
        word_count = len(transcript.split())
        if word_count < 10:
            print("⚠  Too short. Please make a proper argument.")
            continue
        # Do not let interrupt or say-it-again fire
        # on very short transcripts

        # ── Analyse speech ───────────────────────────────────────
        analysis = analyse(transcript, duration)

        # ── Analyse confidence silently ──────────────────────────
        conf_analysis = analyse_confidence(transcript)
        confidence_data.append(conf_analysis)

        # ── Say-it-again-better trigger ──────────────────────────
        redo_triggered = False
        redo_message = ""

        # Level 1 and 2 — never trigger say-it-again
        if level <= 2:
            redo_triggered = False

        # Level 3 only — check specific conditions
        elif level == 3:

            # Condition 1: Way too many definite fillers
            # Only count definite fillers not ambiguous ones
            definite_filler_count = sum(
                f["count"] for f in analysis["filler_words"]
                if f["word"] in {
                    "um", "uh", "ah", "er", "eh", "like",
                    "basically", "literally", "you know",
                    "i mean", "kind of", "sort of", "okay so"
                }
            )
            if definite_filler_count >= 5:
                redo_triggered = True
                redo_message = (
                    "Too many filler words. "
                    "Say it again without them. "
                    "Pause instead of filling silence."
                )

            # Condition 2: Completely unclear argument
            # Only check after turn 2 and only if not
            # already triggered
            elif turn_number > 2 and not redo_triggered:
                is_clear = check_argument_clarity(
                    transcript, turn_number
                )
                if not is_clear:
                    redo_triggered = True
                    redo_message = (
                        "That point was not clear. "
                        "What is your actual argument? "
                        "One sentence. Your position first."
                    )

            # Condition 3: Extremely fast speech
            elif analysis["wpm"] > 200:
                redo_triggered = True
                redo_message = (
                    "Too fast. Say it again slower."
                )

        # IMPORTANT: Never trigger redo more than once
        # per turn. If already triggered, skip all checks.

        if redo_triggered:
            print(f"\n🔄 {redo_message}")
            speak(redo_message)
            redo_input = input(
                "\nPress Enter to try again, "
                "or type 'quit'/'report': "
            ).strip().lower()

            # Allow user to exit or get report from redo prompt
            if redo_input == "quit":
                break
            if redo_input == "report":
                if session_turns:
                    print("\n⏳ Generating your feedback...\n")
                    final_full_report, final_spoken_summary = (
                        generate_report_and_summary(
                            session_id, session_turns,
                            f"Debate Level {level}", topic,
                            confidence_data, level=level
                        )
                    )
                    report_already_generated = True
                break

            silence_seconds = {1: 4.0, 2: 3.0, 3: 2.0}[level]
            audio_array, duration = record_audio(
                max_duration=60,
                silence_duration=silence_seconds
            )

            # Validate redo audio
            valid, reason = is_audio_valid(audio_array)
            if not valid:
                if reason == "too_quiet":
                    print("⚠  No speech detected. "
                          "Please speak clearly into the microphone.")
                elif reason == "too_short":
                    print("⚠  Too short. Please speak for "
                          "at least 2 seconds.")
                else:
                    print("⚠  Could not detect speech. Try again.")
                continue

            print("⏳ Transcribing...")
            transcript = clean_transcript(transcribe(audio_array))
            if not transcript:
                continue
            print(f"\nYou said: {transcript}\n")

            # Word count check on redo transcript
            redo_word_count = len(transcript.split()) if transcript else 0
            if redo_word_count < 10:
                print("⚠  Too short after redo. "
                      "Please make a proper argument.")
                continue
            analysis = analyse(transcript, duration)
            conf_analysis = analyse_confidence(transcript)
            confidence_data[-1] = conf_analysis

        # ── Pick strategy ────────────────────────────────────────
        strategy = pick_strategy(
            recent_strategies, analysis, level,
            turn_number=turn_number,
            topic_change_fired=topic_change_fired,
            just_did_redo=redo_triggered
        )
        if strategy == Strategy.CHANGE_TOPIC:
            topic_change_fired = True
        recent_strategies.append(strategy)
        strategy_instruction = STRATEGY_INSTRUCTIONS[strategy]

        # ── Check interrupt for level 2 and 3 ────────────────────
        # Interrupt fires BEFORE AI response is generated
        # so that TTS fully completes before AI starts
        if level >= 2:
            interrupt_prob = {2: 0.25, 3: 0.50}.get(level, 0)
            if random.random() < interrupt_prob:
                interrupt_openers = [
                    "Wait —",
                    "Stop there —",
                    "Actually —",
                    "Hold on —",
                    "Before you continue —",
                    "That is not right —",
                    "One moment —",
                    "Let me stop you there —",
                    "I have to cut in here —",
                ]
                opener = random.choice(interrupt_openers)
                interrupt_msg = f"{opener} I want to challenge that point."
                print(f"\n⚡ [INTERRUPT] {interrupt_msg}\n")
                speak(interrupt_msg)
                time.sleep(0.5)  # Wait for TTS to fully complete

        # ── Get AI response ──────────────────────────────────────
        ai_response = get_debate_response(
            topic, user_side, ai_side, level,
            history, transcript, strategy_instruction,
            turn_number=turn_number
        )

        print(f"\nAI: {ai_response}\n")
        speak(ai_response)

        # ── Update history ───────────────────────────────────────
        history.append({"role": "user", "content": transcript})
        history.append({"role": "ai", "content": ai_response})

        # ── Build and save turn data ─────────────────────────────
        turn_data = {
            "turn_number": turn_number,
            "transcript": transcript,
            "wpm": analysis["wpm"],
            "filler_count": analysis["total_fillers"],
            "filler_words": [
                f["word"] for f in analysis["filler_words"]
            ],
            "avg_sentence_length": analysis["avg_sentence_length"],
            "duration_seconds": duration,
            "word_count": analysis["word_count"],
            "held_position": analysis["has_clear_opening_position"],
            "used_evidence": any(
                w in transcript.lower() for w in [
                    "for example", "for instance", "such as",
                    "because", "data", "research", "study",
                    "evidence", "proves", "statistics", "fact"
                ]
            ),
            "asked_question": "?" in transcript
        }

        session_turns.append(turn_data)
        save_turn(session_id, turn_data)
        update_session_stats(session_id, session_turns)

    # ── End of session ───────────────────────────────────────────
    # Generate report if not already done
    if session_turns and not report_already_generated:
        speak(
            "Thank you for the session. "
            "Here is your detailed feedback."
        )
        final_full_report, final_spoken_summary = (
            generate_report_and_summary(
                session_id, session_turns,
                f"Debate Level {level}", topic,
                confidence_data, level=level
            )
        )

    # Always speak summary and show full report
    if final_spoken_summary:
        print("\n🔊 Speaking summary...\n")
        speak(final_spoken_summary)

    if final_full_report:
        print("\n" + "─" * 50)
        print("FULL SESSION REPORT")
        print("─" * 50)
        print(final_full_report)
        print("─" * 50)

        # Offer full spoken version
        read_full = input(
            "\nHear full report spoken? (yes/no): "
        ).strip().lower()
        if read_full in ["yes", "y"]:
            speak(final_full_report)


# ═════════════════════════════════════════════════════════════════
#  FREESTYLE MODE
# ═════════════════════════════════════════════════════════════════


def run_freestyle():
    """Run a full freestyle speaking session."""
    prompt_type, prompt_content = get_freestyle_prompt()
    print("\nSpeak for at least 30 seconds.")
    print("Type 'quit' to end. Type 'report' for feedback.")
    input("Press Enter when ready...")

    session_id = create_session(
        mode="freestyle",
        topic=prompt_content[:50]
    )

    history = []
    session_turns = []
    confidence_data = []
    turn_number = 0
    report_already_generated = False
    final_full_report = ""
    final_spoken_summary = ""

    while True:
        turn_number += 1
        print(f"\n─── Turn {turn_number} ───")

        if turn_number > 1:
            user_input_check = input(
                "Press Enter to speak, or type 'quit'/'report': "
            ).strip().lower()
            if user_input_check == "quit":
                break
            if user_input_check == "report":
                if session_turns:
                    print("\n⏳ Generating your feedback...\n")
                    final_full_report, final_spoken_summary = (
                        generate_report_and_summary(
                            session_id, session_turns,
                            "FreeStyle", prompt_content,
                            confidence_data, level=0
                        )
                    )
                    report_already_generated = True
                break

        # ── Record and transcribe ────────────────────────────────
        audio_array, duration = record_audio(
            max_duration=60,
            silence_duration=3.0
        )

        # Validate audio before sending to Whisper
        valid, reason = is_audio_valid(audio_array)
        if not valid:
            if reason == "too_quiet":
                print("⚠  No speech detected. "
                      "Please speak clearly into the microphone.")
            elif reason == "too_short":
                print("⚠  Too short. Please speak for "
                      "at least 2 seconds.")
            else:
                print("⚠  Could not detect speech. Try again.")
            continue

        print("⏳ Transcribing...")
        transcript = clean_transcript(transcribe(audio_array))

        if not transcript or not transcript.strip():
            print("⚠  Nothing detected. Try again.")
            continue

        print(f"\nYou said: {transcript}\n")

        # Minimum 30 seconds check for first turn
        if turn_number == 1 and duration < 20:
            print("⚠  Keep going — try to speak for at least "
                  "30 seconds.")

        analysis = analyse(transcript, duration)
        conf_analysis = analyse_confidence(transcript)
        confidence_data.append(conf_analysis)

        ai_response = get_freestyle_response(
            prompt_type, prompt_content, history, transcript
        )

        print(f"\nAI: {ai_response}\n")
        speak(ai_response)

        history.append({"role": "user", "content": transcript})
        history.append({"role": "ai", "content": ai_response})

        turn_data = {
            "turn_number": turn_number,
            "transcript": transcript,
            "wpm": analysis["wpm"],
            "filler_count": analysis["total_fillers"],
            "filler_words": [
                f["word"] for f in analysis["filler_words"]
            ],
            "avg_sentence_length": analysis["avg_sentence_length"],
            "duration_seconds": duration,
            "word_count": analysis["word_count"],
            "held_position": analysis["has_clear_opening_position"],
            "used_evidence": False,
            "asked_question": "?" in transcript
        }

        session_turns.append(turn_data)
        save_turn(session_id, turn_data)
        update_session_stats(session_id, session_turns)

    # ── End of session ───────────────────────────────────────────
    if session_turns and not report_already_generated:
        speak(
            "Thank you for practising. "
            "Here is your session feedback."
        )
        final_full_report, final_spoken_summary = (
            generate_report_and_summary(
                session_id, session_turns,
                "FreeStyle", prompt_content,
                confidence_data, level=0
            )
        )

    if final_spoken_summary:
        print("\n🔊 Speaking summary...\n")
        speak(final_spoken_summary)

    if final_full_report:
        print("\n" + "─" * 50)
        print("FULL SESSION REPORT")
        print("─" * 50)
        print(final_full_report)
        print("─" * 50)

        read_full = input(
            "\nHear full report spoken? (yes/no): "
        ).strip().lower()
        if read_full in ["yes", "y"]:
            speak(final_full_report)


# ═════════════════════════════════════════════════════════════════
#  WEIRD SITUATION MODE
# ═════════════════════════════════════════════════════════════════

def run_weird_situation():
    """Run a full weird situation speaking session."""
    display_type, content, description = get_weird_situation()
    display_situation(display_type, content)

    print("Describe what you see or tell a story about it.")
    print("Speak naturally — there is no wrong answer.")
    print("Type 'quit' to end. Type 'report' for feedback.")
    input("Press Enter when ready...")

    session_id = create_session(
        mode="weird_situation",
        topic=description[:50]
    )

    history = []
    session_turns = []
    confidence_data = []
    turn_number = 0
    report_already_generated = False
    final_full_report = ""
    final_spoken_summary = ""

    while True:
        turn_number += 1
        print(f"\n─── Turn {turn_number} ───")

        # For turn 1, user already pressed Enter above
        if turn_number > 1:
            user_input_check = input(
                "Press Enter to speak, or type 'quit'/'report': "
            ).strip().lower()
            if user_input_check == "quit":
                break
            if user_input_check == "report":
                if session_turns:
                    print("\n⏳ Generating your feedback...\n")
                    final_full_report, final_spoken_summary = (
                        generate_report_and_summary(
                            session_id, session_turns,
                            "Weird Situation", description,
                            confidence_data, level=0
                        )
                    )
                    report_already_generated = True
                break

        # ── Record and transcribe ────────────────────────────────
        audio_array, duration = record_audio(
            max_duration=60,
            silence_duration=3.0
        )

        # Validate audio before sending to Whisper
        valid, reason = is_audio_valid(audio_array)
        if not valid:
            if reason == "too_quiet":
                print("⚠  No speech detected. "
                      "Please speak clearly into the microphone.")
            elif reason == "too_short":
                print("⚠  Too short. Please speak for "
                      "at least 2 seconds.")
            else:
                print("⚠  Could not detect speech. Try again.")
            continue

        print("⏳ Transcribing...")
        transcript = clean_transcript(transcribe(audio_array))

        if not transcript or not transcript.strip():
            print("⚠  Nothing detected. Try again.")
            continue

        print(f"\nYou said: {transcript}\n")

        analysis = analyse(transcript, duration)
        conf_analysis = analyse_confidence(transcript)
        confidence_data.append(conf_analysis)

        ai_response = get_weird_situation_response(
            description, history, transcript
        )

        print(f"\nAI: {ai_response}\n")
        speak(ai_response)

        history.append({"role": "user", "content": transcript})
        history.append({"role": "ai", "content": ai_response})

        turn_data = {
            "turn_number": turn_number,
            "transcript": transcript,
            "wpm": analysis["wpm"],
            "filler_count": analysis["total_fillers"],
            "filler_words": [
                f["word"] for f in analysis["filler_words"]
            ],
            "avg_sentence_length": analysis["avg_sentence_length"],
            "duration_seconds": duration,
            "word_count": analysis["word_count"],
            "held_position": False,
            "used_evidence": False,
            "asked_question": "?" in transcript
        }

        session_turns.append(turn_data)
        save_turn(session_id, turn_data)
        update_session_stats(session_id, session_turns)

    # ── End of session ───────────────────────────────────────────
    if session_turns and not report_already_generated:
        speak(
            "Thank you for practising. "
            "Here is your session feedback."
        )
        final_full_report, final_spoken_summary = (
            generate_report_and_summary(
                session_id, session_turns,
                "Weird Situation", description,
                confidence_data, level=0
            )
        )

    if final_spoken_summary:
        print("\n🔊 Speaking summary...\n")
        speak(final_spoken_summary)

    if final_full_report:
        print("\n" + "─" * 50)
        print("FULL SESSION REPORT")
        print("─" * 50)
        print(final_full_report)
        print("─" * 50)

        read_full = input(
            "\nHear full report spoken? (yes/no): "
        ).strip().lower()
        if read_full in ["yes", "y"]:
            speak(final_full_report)


# ═════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═════════════════════════════════════════════════════════════════

def main():
    """Main entry point — runs the Phase 2 orchestrator."""
    print(BANNER)
    init_db()
    check_database_status()

    while True:
        mode = select_mode()

        if mode == "freestyle":
            run_freestyle()
        elif mode == "debate_1":
            run_debate(level=1)
        elif mode == "debate_2":
            run_debate(level=2)
        elif mode == "debate_3":
            run_debate(level=3)
        elif mode == "weird_situation":
            run_weird_situation()

        print("\n─────────────────────────────────")
        again = input(
            "Start another session? (yes/no): "
        ).strip().lower()
        if again not in ["yes", "y"]:
            print("\nGood work. See you next session.\n")
            break


if __name__ == "__main__":
    main()
