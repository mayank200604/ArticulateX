# -*- coding: utf-8 -*-
import pytest
from evaluation.pattern_eval import (
    eval_no_grammar_correction,
    eval_no_indian_english_correction,
    eval_no_evidence_demand,
    eval_no_factual_challenge,
    eval_no_intellectual_judgment,
    eval_no_filler_mention,
    eval_no_debate_language,
    eval_no_factual_evaluation,
    eval_no_invented_stats,
    eval_simple_english,
    eval_four_part_structure,
    eval_no_failure_language,
)

def test_eval_no_grammar_correction():
    rule = "AI must never correct grammar or vocabulary"
    turns_pass = [{"turn": 1, "ai_response": "I hear your argument on AI jobs."}]
    turns_fail = [{"turn": 1, "ai_response": "Instead of saying 'AI is good', you should say 'AI is beneficial'."}]
    
    assert eval_no_grammar_correction(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_grammar_correction(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_indian_english_correction():
    rule = "AI must never correct Indian English expressions"
    turns_pass = [{"turn": 1, "ai_response": "Please prepone the meeting."}]
    turns_fail = [{"turn": 1, "ai_response": "Prepone is not standard English, use reschedule instead."}]

    assert eval_no_indian_english_correction(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_indian_english_correction(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_evidence_demand():
    rule = "AI must never ask for data, statistics, evidence, or research"
    turns_pass = [{"turn": 1, "ai_response": "Why do you think so?"}]
    turns_fail = [{"turn": 1, "ai_response": "Give me some statistics or studies that prove your point."}]

    assert eval_no_evidence_demand(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_evidence_demand(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_factual_challenge():
    rule = "AI must never challenge whether argument is factually correct"
    turns_pass = [{"turn": 1, "ai_response": "That's an interesting perspective."}]
    turns_fail = [{"turn": 1, "ai_response": "That claim is incorrect and false."}]

    assert eval_no_factual_challenge(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_factual_challenge(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_intellectual_judgment():
    rule = "AI must never judge intellectual strength of the point"
    turns_pass = [{"turn": 1, "ai_response": "Let's explore your idea."}]
    turns_fail = [{"turn": 1, "ai_response": "That is a shallow and simplistic argument."}]

    assert eval_no_intellectual_judgment(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_intellectual_judgment(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_filler_mention():
    rule = "AI must never mention fillers or delivery issues during turns"
    turns_pass = [{"turn": 1, "ai_response": "Tell me more about your thoughts."}]
    turns_fail = [{"turn": 1, "ai_response": "You used many filler words like um and like."}]

    assert eval_no_filler_mention(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_filler_mention(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_debate_language():
    rule = "No debate or argument in freestyle mode"
    turns_pass = [{"turn": 1, "ai_response": "Tell me more."}]
    turns_fail = [{"turn": 1, "ai_response": "I disagree with you and I counter your claim."}]

    assert eval_no_debate_language(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_no_debate_language(rule, turns_fail)[0]["result"] == "FAIL"

def test_eval_no_factual_evaluation():
    rule = "Feedback must never evaluate factual accuracy"
    feedback_pass = "Your communication flow was clean."
    feedback_fail = "Your argument was factually incorrect."

    assert eval_no_factual_evaluation(rule, [], feedback_text=feedback_pass)[0]["result"] == "PASS"
    assert eval_no_factual_evaluation(rule, [], feedback_text=feedback_fail)[0]["result"] == "FAIL"

def test_eval_no_invented_stats():
    rule = "THREE THINGS TO FIX must not contain invented statistics"
    feedback_pass = "THREE THINGS TO FIX:\n1. Pause more\n2. Vary pitch\n3. Structure sentences."
    feedback_fail = "THREE THINGS TO FIX:\n1. 73% of people prefer structured points according to a study."

    assert eval_no_invented_stats(rule, [], feedback_text=feedback_pass)[0]["result"] == "PASS"
    assert eval_no_invented_stats(rule, [], feedback_text=feedback_fail)[0]["result"] == "FAIL"

def test_eval_simple_english():
    rule = "AI must respond in simple clear English"
    turns_pass = [{"turn": 1, "ai_response": "This is simple language."}]
    turns_fail = [{"turn": 1, "ai_response": "This is characterized by an incomprehensibility and hyper-intellectualization."}]

    assert eval_simple_english(rule, turns_pass)[0]["result"] == "PASS"
    assert eval_simple_english(rule, turns_fail)[0]["result"] == "PARTIAL"

def test_eval_four_part_structure():
    rule = "Each fix must follow four-part structure"
    feedback_pass = "POINT: Pause\nREASON: Breathe\nEXAMPLE: Um\nTRY THIS INSTEAD: Wait"
    feedback_fail = "Just speak slower."

    assert eval_four_part_structure(rule, [], feedback_text=feedback_pass)[0]["result"] == "PASS"
    assert eval_four_part_structure(rule, [], feedback_text=feedback_fail)[0]["result"] == "FAIL"

def test_eval_no_failure_language():
    rule = "Feedback must never use language implying fundamental failure"
    feedback_pass = "You need to work on structure."
    feedback_fail = "You fundamentally failed to communicate and are completely unable to talk."

    assert eval_no_failure_language(rule, [], feedback_text=feedback_pass)[0]["result"] == "PASS"
    assert eval_no_failure_language(rule, [], feedback_text=feedback_fail)[0]["result"] == "FAIL"
