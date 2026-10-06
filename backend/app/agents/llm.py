"""Minimal Gemini client (REST) with function calling and JSON-mode, plus a scripted fake for tests.

NOTE: request/response handling is verified with mock-transport tests. It has not been exercised against
the live Gemini API in the build environment, so treat the first live run as an integration test.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..core.config import Settings, get_settings


class LLMError(RuntimeError):
    pass


@dataclass
class LLMResponse:
    text: str | None = None
    function_calls: list[dict] = field(default_factory=list)  # [{"name":..., "args": {...}}]
    raw_parts: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0


class LLMClient(Protocol):
    model: str

    def generate(self, contents: list[dict], system: str | None = None, tools: list[dict] | None = None,
                 json_schema: dict | None = None) -> LLMResponse: ...


class GeminiClient:
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None):
        self.api_key, self.model = api_key, model
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def generate(self, contents: list[dict], system: str | None = None, tools: list[dict] | None = None,
                 json_schema: dict | None = None) -> LLMResponse:
        body: dict[str, Any] = {"contents": contents, "generationConfig": {"temperature": 0.0}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]
        if json_schema:
            body["generationConfig"].update(responseMimeType="application/json", responseSchema=json_schema)
        started = time.perf_counter()
        last: Exception | None = None
        for attempt in range(3):
            try:
                r = self._client.post(f"{self.BASE}/models/{self.model}:generateContent", json=body,
                                      headers={"x-goog-api-key": self.api_key})
                if r.status_code in (429, 500, 502, 503, 504):
                    last = LLMError(f"Gemini returned {r.status_code}")
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"Gemini error {r.status_code}")
                return self._parse(r.json(), (time.perf_counter() - started) * 1000)
            except httpx.HTTPError as exc:
                last = exc
                time.sleep(0.5 * (2 ** attempt))
        raise LLMError(f"Gemini request failed: {last}")

    @staticmethod
    def _parse(data: dict, latency_ms: float) -> LLMResponse:
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError("Gemini returned no candidates (possibly blocked)")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text_bits = [p["text"] for p in parts if "text" in p and not p.get("thought")]
        calls = [{"name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}}
                 for p in parts if "functionCall" in p]
        u = data.get("usageMetadata") or {}
        usage = {"prompt_tokens": u.get("promptTokenCount", 0), "output_tokens": u.get("candidatesTokenCount", 0),
                 "total_tokens": u.get("totalTokenCount", 0)}
        return LLMResponse(text="".join(text_bits) or None, function_calls=calls, raw_parts=parts,
                           usage=usage, latency_ms=latency_ms)


class ScriptedLLM:
    """Test double: returns pre-scripted responses in order and records what it was sent."""

    model = "scripted"

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def generate(self, contents, system=None, tools=None, json_schema=None) -> LLMResponse:
        self.requests.append({"contents": contents, "system": system, "tools": tools, "json_schema": json_schema})
        if not self.responses:
            raise LLMError("ScriptedLLM has no more responses")
        return self.responses.pop(0)


def get_llm(settings: Settings | None = None) -> LLMClient | None:
    s = settings or get_settings()
    if s.effective_mode != "llm" or not s.gemini_api_key:
        return None
    return GeminiClient(s.gemini_api_key, s.gemini_model, s.llm_timeout_s)
