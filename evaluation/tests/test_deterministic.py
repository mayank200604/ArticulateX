# -*- coding: utf-8 -*-
import pytest
from evaluation.deterministic_eval import (
    _count_sentences,
    eval_sentence_count_1_2,
    eval_sentence_count_2_3,
    eval_banned_phrases,
    eval_sentence_starter_variety,
    eval_exactly_one_question,
    eval_zero_interrupts,
    eval_interrupt_variation,
    eval_feedback_banned_phrase,
    eval_feedback_has_section,
)

def test_count_sentences():
    assert _count_sentences("Hello world.") == 1
    assert _count_sentences("Hello world! How are you? Fine.") == 3
    assert _count_sentences("") == 0
    assert _count_sentences("No punctuation") == 1

def test_eval_sentence_count_1_2():
    rule = "AI response must be 1-2 sentences maximum"
    turns_pass = [
        {"turn": 1, "ai_response": "Hello world."},
        {"turn": 2, "ai_response": "One sentence. Two sentences."},
    ]
    turns_fail = [
        {"turn": 1, "ai_response": "One. Two. Three."},
    ]
    res_pass = eval_sentence_count_1_2(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_sentence_count_1_2(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"
    assert "Turn 1" in res_fail[0]["reason"]

def test_eval_sentence_count_2_3():
    rule = "Maximum 2-3 sentences per response"
    turns_pass = [
        {"turn": 1, "ai_response": "One. Two. Three."},
    ]
    turns_fail = [
        {"turn": 1, "ai_response": "One. Two. Three. Four."},
    ]
    res_pass = eval_sentence_count_2_3(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_sentence_count_2_3(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_banned_phrases():
    rule = "AI must never use banned phrases: great point..."
    turns_pass = [
        {"turn": 1, "ai_response": "That is an interesting topic."}, # wait, interesting is banned in freestyle. Let's check BANNED_PHRASES list
    ]
    # In deterministic_eval.py: BANNED_PHRASES has "interesting", "great point", etc.
    # So "interesting" is banned. Let's use a safe pass phrase.
    turns_safe = [
        {"turn": 1, "ai_response": "I see what you mean. Let's discuss further."},
    ]
    turns_fail = [
        {"turn": 1, "ai_response": "That is a great point."},
    ]
    res_pass = eval_banned_phrases(rule, turns_safe)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_banned_phrases(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_sentence_starter_variety():
    rule = "AI must vary sentence starter every turn"
    turns_pass = [
        {"turn": 1, "ai_response": "Hello my friend."},
        {"turn": 2, "ai_response": "Welcome to the show."},
    ]
    turns_fail = [
        {"turn": 1, "ai_response": "Hello friend."},
        {"turn": 2, "ai_response": "Hello user."},
    ]
    res_pass = eval_sentence_starter_variety(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_sentence_starter_variety(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_exactly_one_question():
    rule = "AI must ask exactly ONE follow-up question per turn"
    turns_pass = [
        {"turn": 1, "ai_response": "What do you think?"},
        {"turn": 2, "ai_response": "Can you elaborate?"},
    ]
    turns_fail = [
        {"turn": 1, "ai_response": "Hello world."}, # 0 questions
    ]
    turns_partial = [
        {"turn": 1, "ai_response": "What? Why?"}, # 2 questions
        {"turn": 2, "ai_response": "Where?"}, # 1 question
    ]
    res_pass = eval_exactly_one_question(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_exactly_one_question(rule, turns_fail)
    assert res_fail[0]["result"] in ("FAIL", "PARTIAL")

    res_part = eval_exactly_one_question(rule, turns_partial)
    assert res_part[0]["result"] in ("FAIL", "PARTIAL")

def test_eval_zero_interrupts():
    rule = "Zero interruptions"
    turns_pass = [
        {"turn": 1, "is_interrupt": False},
        {"turn": 2, "is_interrupt": False},
    ]
    turns_fail = [
        {"turn": 1, "is_interrupt": False},
        {"turn": 2, "is_interrupt": True},
    ]
    res_pass = eval_zero_interrupts(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_zero_interrupts(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_interrupt_variation():
    rule = "Interrupt phrases must vary"
    turns_pass = [
        {"turn": 1, "is_interrupt": True, "ai_response": "Wait, what about X?"},
        {"turn": 2, "is_interrupt": True, "ai_response": "Hold on, is that true?"},
    ]
    turns_fail = [
        {"turn": 1, "is_interrupt": True, "ai_response": "Hold on a minute."},
        {"turn": 2, "is_interrupt": True, "ai_response": "Hold on, why?"},
    ]
    res_pass = eval_interrupt_variation(rule, turns_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_interrupt_variation(rule, turns_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_feedback_banned_phrase():
    rule = "Feedback must never say 'hesitant and unclear'"
    feedback_pass = "The user spoke clearly and with conviction."
    feedback_fail = "The user was hesitant and unclear during the debate."

    res_pass = eval_feedback_banned_phrase(rule, [], feedback_text=feedback_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_feedback_banned_phrase(rule, [], feedback_text=feedback_fail)
    assert res_fail[0]["result"] == "FAIL"

def test_eval_feedback_has_section():
    rule = "ONE EARNED ENCOURAGEMENT is mandatory"
    feedback_pass = "Here is some EARNED ENCOURAGEMENT: you did great!"
    feedback_fail = "Fluency fixes: Speak louder."

    res_pass = eval_feedback_has_section(rule, [], feedback_text=feedback_pass)
    assert res_pass[0]["result"] == "PASS"

    res_fail = eval_feedback_has_section(rule, [], feedback_text=feedback_fail)
    assert res_fail[0]["result"] == "FAIL"
