# -*- coding: utf-8 -*-
"""
provider_manager.py — Multi-provider LLM management with rate limiting.

Features:
- Provider priority ordering (Groq → Gemini → OpenAI → Anthropic)
- Per-provider request tracking with sliding window
- Automatic cooldown after rate limit detection
- Exponential backoff with configurable max retries
- Never retries a rate-limited provider within its cooldown window
- JSON parse failure recovery with raw-text fallback
"""

import os
import re
import json
import time
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from evaluation.config import (
    PROVIDERS, MAX_LLM_RETRIES, INITIAL_RETRY_DELAY,
    EVAL_TEMPERATURE, EVAL_MAX_TOKENS,
)
from evaluation.api_tracker import APITracker


class ProviderState:
    """Tracks the health and usage of a single provider."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.request_timestamps = []   # sliding window for RPM
        self.daily_requests = 0
        self.cooldown_until = 0.0      # timestamp when cooldown expires
        self.consecutive_failures = 0
        self.total_requests = 0
        self.total_failures = 0

    @property
    def is_enabled(self) -> bool:
        return self.config.get("enabled", False)

    @property
    def is_in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        remaining = self.cooldown_until - time.time()
        return max(0.0, remaining)

    @property
    def rpm_usage(self) -> int:
        """Requests in the last 60 seconds."""
        cutoff = time.time() - 60
        self.request_timestamps = [
            t for t in self.request_timestamps if t > cutoff
        ]
        return len(self.request_timestamps)

    @property
    def is_rpm_available(self) -> bool:
        return self.rpm_usage < self.config.get("rpm_limit", 30)

    @property
    def is_available(self) -> bool:
        return (
            self.is_enabled
            and not self.is_in_cooldown
            and self.is_rpm_available
            and self.daily_requests < self.config.get("rpd_limit", 99999)
        )

    def record_request(self):
        self.request_timestamps.append(time.time())
        self.daily_requests += 1
        self.total_requests += 1
        self.consecutive_failures = 0

    def record_failure(self, is_rate_limit: bool = False):
        self.consecutive_failures += 1
        self.total_failures += 1
        if is_rate_limit:
            cooldown = self.config.get("cooldown_seconds", 65)
            # Double cooldown on repeated rate limits
            if self.consecutive_failures > 1:
                cooldown *= min(self.consecutive_failures, 4)
            self.cooldown_until = time.time() + cooldown

    def status(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.is_enabled,
            "available": self.is_available,
            "in_cooldown": self.is_in_cooldown,
            "cooldown_remaining_s": round(self.cooldown_remaining, 1),
            "rpm_usage": self.rpm_usage,
            "rpm_limit": self.config.get("rpm_limit", 0),
            "daily_requests": self.daily_requests,
            "daily_limit": self.config.get("rpd_limit", 0),
            "consecutive_failures": self.consecutive_failures,
        }


class ProviderManager:
    """
    Manages multiple LLM providers with intelligent failover.

    Tries providers in priority order. Detects rate limits and
    enters cooldown. Never retries a provider that's rate-limited.
    """

    def __init__(self, tracker: Optional[APITracker] = None):
        self.tracker = tracker or APITracker()
        self.providers = {}
        for name, cfg in sorted(
            PROVIDERS.items(), key=lambda x: x[1].get("priority", 99)
        ):
            self.providers[name] = ProviderState(name, cfg)

    def get_healthy_provider(self) -> Optional[ProviderState]:
        """Return the highest-priority available provider."""
        for prov in self.providers.values():
            if prov.is_available:
                return prov
        return None

    def wait_for_provider(self, timeout: float = 300) -> Optional[ProviderState]:
        """Wait until a provider becomes available or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            prov = self.get_healthy_provider()
            if prov:
                return prov

            # Find the shortest cooldown
            min_wait = min(
                (p.cooldown_remaining for p in self.providers.values()
                 if p.is_enabled and p.is_in_cooldown),
                default=5.0
            )
            wait_time = min(max(min_wait, 1.0), 30.0)
            print(f"  ⏳ All providers busy. Waiting {wait_time:.0f}s...")
            time.sleep(wait_time)

        return None

    def call(
        self,
        messages: list,
        json_mode: bool = False,
        scenario: str = "",
        category: str = "",
    ) -> str:
        """
        Call LLM with provider failover and exponential backoff.

        Returns the response text. Raises Exception if all providers fail.
        """
        errors = []

        for prov in self.providers.values():
            if not prov.is_available:
                continue

            delay = INITIAL_RETRY_DELAY
            for attempt in range(MAX_LLM_RETRIES):
                start_time = time.time()
                try:
                    content = self._call_provider(prov, messages, json_mode)
                    latency = (time.time() - start_time) * 1000

                    # Estimate tokens (rough)
                    tokens_in = sum(len(m.get("content", "")) for m in messages) // 4
                    tokens_out = len(content) // 4

                    prov.record_request()
                    self.tracker.record(
                        provider=prov.name,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=latency,
                        success=True,
                        scenario=scenario,
                        category=category,
                    )

                    # Validate JSON if required
                    if json_mode:
                        content = self._ensure_valid_json(content)

                    return content

                except Exception as exc:
                    latency = (time.time() - start_time) * 1000
                    exc_str = str(exc).lower()
                    is_rate_limit = any(kw in exc_str for kw in [
                        "rate limit", "429", "limit reached",
                        "resource_exhausted", "quota", "too many"
                    ])
                    is_server_error = any(kw in exc_str for kw in [
                        "503", "500", "timeout", "connection",
                        "unavailable", "overloaded"
                    ])

                    if is_rate_limit:
                        prov.record_failure(is_rate_limit=True)
                        self.tracker.record(
                            provider=prov.name, latency_ms=latency,
                            success=False, scenario=scenario,
                            category=category,
                            error=f"Rate limited: {str(exc)[:100]}",
                        )
                        print(f"  ⚠ {prov.name} rate limited. "
                              f"Cooldown {prov.cooldown_remaining:.0f}s. "
                              f"Trying next provider...")
                        errors.append(f"{prov.name}: rate limited")
                        break  # Move to next provider

                    if is_server_error and attempt < MAX_LLM_RETRIES - 1:
                        prov.record_failure(is_rate_limit=False)
                        self.tracker.record(
                            provider=prov.name, latency_ms=latency,
                            success=False, scenario=scenario,
                            category=category,
                            error=f"Server error (retry {attempt+1}): {str(exc)[:100]}",
                        )
                        print(f"  ⚠ {prov.name} error (attempt {attempt+1}/{MAX_LLM_RETRIES}): "
                              f"{str(exc)[:80]}. Retrying in {delay:.1f}s...")
                        time.sleep(delay)
                        delay *= 2  # Exponential backoff
                        continue

                    # Non-retryable error
                    prov.record_failure(is_rate_limit=False)
                    self.tracker.record(
                        provider=prov.name, latency_ms=latency,
                        success=False, scenario=scenario,
                        category=category,
                        error=f"Fatal: {str(exc)[:100]}",
                    )
                    errors.append(f"{prov.name}: {str(exc)[:80]}")
                    print(f"  ✗ {prov.name} failed: {str(exc)[:80]}. "
                          f"Trying next provider...")
                    break  # Move to next provider

        # All providers failed — try waiting for cooldown recovery
        print("  ⏳ All providers exhausted. Waiting for recovery...")
        prov = self.wait_for_provider(timeout=120)
        if prov:
            try:
                content = self._call_provider(prov, messages, json_mode)
                prov.record_request()
                if json_mode:
                    content = self._ensure_valid_json(content)
                return content
            except Exception as exc:
                errors.append(f"{prov.name} (recovery): {str(exc)[:80]}")

        raise Exception(
            f"All LLM providers failed after retries. Errors: {'; '.join(errors)}"
        )

    def _call_provider(
        self, prov: ProviderState, messages: list, json_mode: bool
    ) -> str:
        """Make the actual API call to a specific provider."""
        if prov.name == "groq":
            return self._call_groq(prov, messages, json_mode)
        elif prov.name == "gemini":
            return self._call_gemini(prov, messages, json_mode)
        elif prov.name == "openai":
            return self._call_openai(prov, messages, json_mode)
        elif prov.name == "anthropic":
            return self._call_anthropic(prov, messages, json_mode)
        else:
            raise ValueError(f"Unknown provider: {prov.name}")

    def _call_groq(
        self, prov: ProviderState, messages: list, json_mode: bool
    ) -> str:
        from groq import Groq
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        extra = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(
            model=prov.config["model"],
            messages=messages,
            temperature=EVAL_TEMPERATURE,
            max_tokens=EVAL_MAX_TOKENS if json_mode else 100,
            **extra,
        )
        return resp.choices[0].message.content.strip()

    def _call_gemini(
        self, prov: ProviderState, messages: list, json_mode: bool
    ) -> str:
        from google import genai as google_genai
        from google.genai import types
        client = google_genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

        # Flatten messages to single prompt
        prompt = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        config = types.GenerateContentConfig(
            temperature=EVAL_TEMPERATURE,
            max_output_tokens=EVAL_MAX_TOKENS if json_mode else 100,
        )
        if json_mode:
            config.response_mime_type = "application/json"

        resp = client.models.generate_content(
            model=prov.config["model"],
            contents=prompt,
            config=config,
        )
        return resp.text.strip()

    def _call_openai(
        self, prov: ProviderState, messages: list, json_mode: bool
    ) -> str:
        import openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        extra = {}
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(
            model=prov.config["model"],
            messages=messages,
            temperature=EVAL_TEMPERATURE,
            max_tokens=EVAL_MAX_TOKENS if json_mode else 100,
            **extra,
        )
        return resp.choices[0].message.content.strip()

    def _call_anthropic(
        self, prov: ProviderState, messages: list, json_mode: bool
    ) -> str:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Convert messages to Anthropic format
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append({
                    "role": m["role"],
                    "content": m["content"],
                })
        if not user_msgs:
            user_msgs = [{"role": "user", "content": system_msg}]
            system_msg = ""

        extra = {}
        if system_msg:
            extra["system"] = system_msg

        resp = client.messages.create(
            model=prov.config["model"],
            messages=user_msgs,
            temperature=EVAL_TEMPERATURE,
            max_tokens=EVAL_MAX_TOKENS if json_mode else 100,
            **extra,
        )
        return resp.content[0].text.strip()

    def _ensure_valid_json(self, content: str) -> str:
        """
        Validate and recover JSON from LLM response.
        Handles common failures: markdown fences, trailing text, broken quotes.
        """
        # Try direct parse first
        try:
            json.loads(content)
            return content
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
            try:
                json.loads(cleaned)
                return cleaned
            except json.JSONDecodeError:
                pass

        # Try to extract JSON object from surrounding text
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                json.loads(match.group())
                return match.group()
            except json.JSONDecodeError:
                pass

        # Try to extract JSON array from surrounding text
        match = re.search(r'\[[\s\S]*\]', content)
        if match:
            try:
                json.loads(match.group())
                return match.group()
            except json.JSONDecodeError:
                pass

        # Last resort: return a valid empty evaluations JSON
        print(f"  ⚠ JSON parse recovery failed. Raw content: {content[:200]}...")
        return '{"evaluations": []}'

    def status(self) -> dict:
        """Status of all providers."""
        return {
            name: prov.status()
            for name, prov in self.providers.items()
        }
