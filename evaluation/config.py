# -*- coding: utf-8 -*-
"""
config.py — Central configuration for the evaluation framework.

Mode presets, provider settings, feature flags, cost estimates.
"""

import os

# ════════════════════════════════════════════════════════════════
# EVALUATION MODE PRESETS
# ════════════════════════════════════════════════════════════════

FAST_MODE = {
    "name": "fast",
    "description": "Quick development testing — 3 scenarios, 5 turns each",
    "max_scenarios": 3,
    "max_turns": 5,
    "scenario_selection": [
        "FreeStyle — Random Word",
        "Debate Level 1",
        "Weird Situation",
    ],
}

FULL_MODE = {
    "name": "full",
    "description": "Complete validation — all scenarios, full turns",
    "max_scenarios": None,   # no limit
    "max_turns": None,       # use all defined turns
    "scenario_selection": None,  # all scenarios
}

# ════════════════════════════════════════════════════════════════
# LLM EVALUATION SETTINGS
# ════════════════════════════════════════════════════════════════

# Maximum rules per LLM batch call — prevents token overflow
MAX_RULES_PER_BATCH = 15

# Maximum retries for LLM calls
MAX_LLM_RETRIES = 3

# Initial delay for exponential backoff (seconds)
INITIAL_RETRY_DELAY = 2.0

# LLM temperature for evaluation (low = deterministic)
EVAL_TEMPERATURE = 0.0

# Max output tokens for evaluation responses
EVAL_MAX_TOKENS = 4000

# ════════════════════════════════════════════════════════════════
# PROVIDER CONFIGURATION
# ════════════════════════════════════════════════════════════════

PROVIDERS = {
    "groq": {
        "priority": 1,
        "model": "llama-3.3-70b-versatile",
        "rpm_limit": 30,        # requests per minute
        "rpd_limit": 14400,     # requests per day
        "tpm_limit": 131072,    # tokens per minute (input)
        "cooldown_seconds": 65, # wait after rate limit
        "cost_per_1k_input": 0.0,   # free tier
        "cost_per_1k_output": 0.0,
        "enabled": True,
    },
    "gemini": {
        "priority": 2,
        "model": "gemini-2.0-flash",
        "rpm_limit": 15,
        "rpd_limit": 1500,
        "tpm_limit": 1000000,
        "cooldown_seconds": 65,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "enabled": True,
    },
    "openai": {
        "priority": 3,
        "model": "gpt-4o-mini",
        "rpm_limit": 500,
        "rpd_limit": 10000,
        "tpm_limit": 200000,
        "cooldown_seconds": 10,
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
        "enabled": bool(os.getenv("OPENAI_API_KEY")),
    },
    "anthropic": {
        "priority": 4,
        "model": "claude-sonnet-4-20250514",
        "rpm_limit": 50,
        "rpd_limit": 5000,
        "tpm_limit": 80000,
        "cooldown_seconds": 30,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
    },
}

# ════════════════════════════════════════════════════════════════
# FEATURE FLAGS
# ════════════════════════════════════════════════════════════════

# Skip TTS during test runs (saves Google Cloud TTS quota)
SKIP_TTS = os.getenv("EVAL_SKIP_TTS", "true").lower() == "true"

# Enable evaluation caching
USE_CACHE = os.getenv("EVAL_USE_CACHE", "true").lower() == "true"

# Cache file location
CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "evaluation_cache.json"
)

# Report output directory
REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "eval_reports"
)

# ════════════════════════════════════════════════════════════════
# TOKEN ESTIMATION
# ════════════════════════════════════════════════════════════════

# Average tokens per character (rough estimate for English)
TOKENS_PER_CHAR = 0.25

# Average input tokens for a batch evaluation prompt
AVG_EVAL_INPUT_TOKENS = 2000

# Average output tokens for a batch evaluation response
AVG_EVAL_OUTPUT_TOKENS = 1500

# Average input tokens for a conversation turn (server-side)
AVG_TURN_INPUT_TOKENS = 1200

# Average output tokens for a conversation turn
AVG_TURN_OUTPUT_TOKENS = 100

# Average input tokens for feedback generation
AVG_FEEDBACK_INPUT_TOKENS = 3000

# Average output tokens for feedback generation
AVG_FEEDBACK_OUTPUT_TOKENS = 900
