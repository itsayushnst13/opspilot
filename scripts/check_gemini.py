#!/usr/bin/env python3
"""Verify the Gemini integration against the live API. Run from the repository root:

    python scripts/check_gemini.py

It reads GEMINI_API_KEY from the environment or .env, never prints it, and redacts it from every
message. It (1) lists the models this account can actually call, (2) reports which of the configured
models are usable, and (3) makes one real generateContent call through the application's own client,
so a success here means the app itself can generate. Exit code 0 = Gemini generated text.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BASE = "https://generativelanguage.googleapis.com/v1beta"


def redact(text: str, key: str) -> str:
    return text.replace(key, "[REDACTED]") if key else text


def list_models(key: str, timeout: float, client: httpx.Client | None = None) -> tuple[list[str], str | None]:
    """Model names that support generateContent, or an error string. `client` is for tests."""
    http = client or httpx.Client(timeout=timeout)
    try:
        r = http.get(f"{BASE}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200})
    except httpx.HTTPError as exc:
        return [], f"network error: {redact(str(exc), key)[:200]}"
    if r.status_code >= 400:
        try:
            msg = (r.json().get("error") or {}).get("message", "")
        except ValueError:
            msg = ""
        return [], f"HTTP {r.status_code}: {redact(' '.join(msg.split()), key)[:200]}"
    names = [m.get("name", "").removeprefix("models/") for m in (r.json().get("models") or [])
             if "generateContent" in (m.get("supportedGenerationMethods") or [])]
    return sorted(n for n in names if n), None


def time_one(key: str, model: str, level: str | None, s) -> str:
    """One live call with a fixed model and thinking level. Returns a one-line result."""
    from app.agents.llm import GeminiClient, LLMError

    c = GeminiClient(key, model, s.llm_timeout_s, fallback_models=[], thinking_level=level,
                     budget_s=s.llm_total_budget_s)
    started = time.perf_counter()
    try:
        r = c.generate([{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}])
    except LLMError as exc:
        return f"{model:<20} {str(level or 'default'):<8} FAILED ({exc.category}) {redact(str(exc), key)[:80]}"
    ms = (time.perf_counter() - started) * 1000
    note = "  <- thinkingConfig REJECTED by the API, sent without it" if c.dropped_optional else ""
    return (f"{model:<20} {str(level or 'default'):<8} {ms:7.0f} ms  "
            f"thinking tokens {r.usage.get('thoughts_tokens', 0):<5} total {r.usage.get('total_tokens', 0)}{note}")


def compare(key: str, s, models: list[str]) -> int:
    print("\nLatency by model and thinking level (one live call each):\n")
    print(f"{'MODEL':<20} {'THINKING':<8} {'LATENCY':>10}")
    for model in models[:2]:
        for level in (None, "low", "minimal"):
            print("  " + time_one(key, model, level, s))
    print("\nPick the fastest row that still answers, then set GEMINI_MODEL and GEMINI_THINKING_LEVEL.")
    return 0


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        from dotenv import dotenv_values  # provided by pydantic-settings' dependency set
        key = (dotenv_values(ROOT / ".env") or {}).get("GEMINI_API_KEY")
    if not key:
        print("FAIL  no GEMINI_API_KEY in the environment or .env")
        return 1
    print("ok    API key found (its value is never printed)")

    os.environ["GEMINI_API_KEY"] = key
    os.environ["LLM_MODE"] = "llm"
    from app.agents.llm import LLMError, get_llm, reset_model_cache
    from app.core.config import Settings

    s = Settings()
    configured = [s.gemini_model] + [m.strip() for m in s.gemini_fallback_models.split(",") if m.strip()]
    print(f"      configured models: {', '.join(configured)}")

    available, error = list_models(key, s.llm_timeout_s)
    if error:
        print(f"FAIL  could not list models - {error}")
        if error.startswith(("HTTP 401", "HTTP 403")):
            print("      -> the API rejected the key: create a new one in Google AI Studio and set GEMINI_API_KEY")
        elif error.startswith("network"):
            print("      -> generativelanguage.googleapis.com was not reachable from here (proxy, firewall or")
            print("         no internet). Run this on a machine with direct internet access.")
        return 1
    print(f"ok    {len(available)} models support generateContent for this account")
    usable = [m for m in configured if m in available]
    missing = [m for m in configured if m not in available]
    if usable:
        print(f"ok    usable from your configuration: {', '.join(usable)}")
    if missing:
        print(f"WARN  not available to this account: {', '.join(missing)}")
    if not usable:
        suggestion = [m for m in available if "flash" in m and "image" not in m and "tts" not in m]
        print("FAIL  none of the configured models is available.")
        print(f"      set GEMINI_MODEL to one of: {', '.join(suggestion[:5]) or ', '.join(available[:5])}")
        return 1

    reset_model_cache()
    client = get_llm(s)
    started = time.perf_counter()
    try:
        r = client.generate([{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}])
    except LLMError as exc:
        print(f"FAIL  generation failed ({exc.category}): {redact(str(exc), key)[:300]}")
        print("      the app would fall back to rules mode and flag LLM_UNAVAILABLE on the run")
        return 1
    ms = (time.perf_counter() - started) * 1000
    if not (r.text or r.function_calls):
        print(f"FAIL  {r.model} answered with no text and no function call")
        return 1
    print(f"ok    {r.model} generated a response in {ms:.0f} ms")
    print(f"      tokens in/out/total: {r.usage.get('prompt_tokens')}/"
          f"{r.usage.get('output_tokens')}/{r.usage.get('total_tokens')}")
    print(f"      text: {(r.text or '').strip()[:60]!r}")
    if r.model != s.gemini_model:
        print(f"      NOTE: the fallback model answered. Set GEMINI_MODEL={r.model} so it is tried first.")
    if r.usage.get("thoughts_tokens"):
        print(f"      thinking tokens: {r.usage['thoughts_tokens']} (these are what make a trivial call slow)")
    print("PASS  live Gemini generation works; this was not a rules-mode fallback")
    if "--compare" in sys.argv:
        return compare(key, s, usable)
    if ms > 10000:
        print(f"WARN  {ms:.0f} ms for a one-word answer. An RFQ run makes several calls in sequence.")
        print("      Re-run with --compare to time each model and thinking level, then set the fastest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
