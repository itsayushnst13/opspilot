"""Minimal Gemini client (REST) with function calling and JSON-mode, plus a scripted fake for tests.

NOTE: request/response handling is verified with mock-transport tests ONLY. It has not yet been
exercised successfully against the live Gemini API, so treat the first live run as an integration
test: `python scripts/check_gemini.py` checks the key, lists the models the account can actually
use, and makes one real generation call without ever printing the key.

Design notes
* Model names get retired, so the client walks a configured fallback list and remembers what worked.
* Every failure is classified (auth / model_missing / rate_limit / outage / timeout / network /
  invalid_request / blocked) so a caller can tell "the provider is down" from "the key is wrong".
* A total time budget bounds attempts x fallback models, so an outage cannot multiply into minutes.
* The API key is redacted from every message raised here.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..core.config import Settings, get_settings

#: Transient upstream conditions: retry the same model, then move on to the next one.
TRANSIENT_STATUS = (429, 500, 502, 503, 504)
#: Failures that no other model can fix, so they stop the whole call immediately.
FATAL_CATEGORIES = ("auth", "blocked")


class LLMError(RuntimeError):
    """A Gemini call that produced no response, with a machine-readable category."""

    def __init__(self, message: str, category: str = "unknown", status: int | None = None,
                 model: str | None = None):
        super().__init__(message)
        self.category = category
        self.status = status
        self.model = model


@dataclass
class LLMResponse:
    text: str | None = None
    function_calls: list[dict] = field(default_factory=list)  # [{"name":..., "args": {...}}]
    raw_parts: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    model: str = ""


class LLMClient(Protocol):
    model: str

    def generate(self, contents: list[dict], system: str | None = None, tools: list[dict] | None = None,
                 json_schema: dict | None = None) -> LLMResponse: ...


_LOCK = threading.Lock()
_WORKING_MODEL: dict[str, str] = {}  # configured primary model -> model that actually answered
_STATUS: dict[str, Any] = {"verified": False, "model": None, "error": None, "category": None, "at": None}


def llm_status() -> dict:
    """What the last Gemini call in this process actually did. Contains no secrets."""
    with _LOCK:
        return dict(_STATUS)


def reset_model_cache() -> None:
    """Forget the remembered model and the last status (used by tests and on config changes)."""
    with _LOCK:
        _WORKING_MODEL.clear()
        _STATUS.update(verified=False, model=None, error=None, category=None, at=None)


def _record_success(primary: str, model: str) -> None:
    with _LOCK:
        _WORKING_MODEL[primary] = model
        _STATUS.update(verified=True, model=model, error=None, category=None, at=time.time())


def _record_failure(error: LLMError) -> None:
    with _LOCK:
        _STATUS.update(verified=False, error=str(error)[:500], category=error.category, at=time.time())


def _forget(primary: str, model: str) -> None:
    """Drop a remembered model that has since been retired, so it is not tried first again."""
    with _LOCK:
        if _WORKING_MODEL.get(primary) == model:
            _WORKING_MODEL.pop(primary, None)


def _api_error_message(r: httpx.Response, api_key: str = "") -> str:
    """Extract a short Gemini error message without exposing the API key."""
    try:
        msg = (r.json().get("error") or {}).get("message") or ""
    except (ValueError, AttributeError):
        msg = ""
    msg = " ".join(str(msg).split())[:500]
    if api_key:
        msg = msg.replace(api_key, "[REDACTED]")
    return msg or "No error message provided"


def _retry_after(r: httpx.Response) -> float | None:
    """Seconds the API asks us to wait (RetryInfo in the error details), if it said so."""
    try:
        for d in ((r.json().get("error") or {}).get("details") or []):
            delay = str(d.get("retryDelay", ""))
            if delay.endswith("s") and delay[:-1].replace(".", "", 1).isdigit():
                return float(delay[:-1])
    except (ValueError, AttributeError):
        pass
    return None


def _api_error_status(r: httpx.Response) -> str:
    try:
        return (r.json().get("error") or {}).get("status", "") or ""
    except (ValueError, AttributeError):
        return ""


def _is_model_missing(r: httpx.Response, api_key: str = "") -> bool:
    """True when this model name is unusable but another model might work."""
    if r.status_code == 404:
        return True
    if r.status_code == 400:
        msg = _api_error_message(r, api_key).lower()
        return "model" in msg and ("not found" in msg or "not available" in msg)
    return False


def _category(status: int) -> str:
    if status in (401, 403):
        return "auth"          # a different model will not fix a bad or unauthorised key
    if status == 429:
        return "rate_limit"
    if status in (500, 502, 503, 504):
        return "outage"
    return "invalid_request"


class GeminiClient:
    BASE = "https://generativelanguage.googleapis.com/v1beta"
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        fallback_models: list[str] | None = None,
        temperature: float | None = None,
        thinking_level: str | None = None,
        budget_s: float | None = None,
    ):
        self.api_key = api_key
        self.primary = model
        self.fallbacks = [m for m in (fallback_models or []) if m and m != model]
        self.temperature = temperature
        self.thinking_level = thinking_level or None
        self.timeout = timeout
        # Bound the whole call (attempts x models), not just one request.
        self.budget_s = budget_s if budget_s and budget_s > 0 else timeout + 30.0
        self.model = _WORKING_MODEL.get(model, model)
        #: True once an optional generationConfig field was rejected and dropped for this client.
        self.dropped_optional = False
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def _candidates(self) -> list[str]:
        """Remembered model first, then the configured primary, then the fallbacks; no duplicates."""
        return list(dict.fromkeys([self.model, self.primary, *self.fallbacks]))

    def _safe(self, exc: Exception) -> str:
        text = str(exc) or exc.__class__.__name__
        if self.api_key:
            text = text.replace(self.api_key, "[REDACTED]")
        return text[:300]

    def _body(self, contents: list[dict], system: str | None, tools: list[dict] | None,
              json_schema: dict | None, with_optional: bool = True) -> dict:
        gen: dict[str, Any] = {}
        if self.temperature is not None:
            # Gemini 3 models are documented to work best at their default temperature, so the
            # field is only sent when it has been configured explicitly.
            gen["temperature"] = self.temperature
        if with_optional and self.thinking_level:
            # Verified live: a flat generationConfig.thinkingLevel is rejected; it nests here.
            gen["thinkingConfig"] = {"thinkingLevel": self.thinking_level}
        if json_schema:
            gen.update(responseMimeType="application/json", responseSchema=json_schema)
        body: dict[str, Any] = {"contents": contents}
        if gen:
            body["generationConfig"] = gen
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{"functionDeclarations": tools}]
        return body

    def _call(self, model: str, body: dict, timeout: float, started: float) -> LLMResponse:
        """One request. Raises a categorised LLMError; never returns a partial result."""
        try:
            r = self._client.post(f"{self.BASE}/models/{model}:generateContent", json=body,
                                  headers={"x-goog-api-key": self.api_key}, timeout=timeout)
        except httpx.TimeoutException as exc:
            raise LLMError(f"{model}: request timed out after {timeout:.0f}s ({self._safe(exc)})",
                           "timeout", None, model) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{model}: network error ({self._safe(exc)})", "network", None, model) from exc

        if _is_model_missing(r, self.api_key):
            raise LLMError(f"{model}: HTTP {r.status_code}: {_api_error_message(r, self.api_key)}",
                           "model_missing", r.status_code, model)
        if r.status_code >= 400:
            status = _api_error_status(r)
            detail = f", status={status}" if status else ""
            exc = LLMError(f"{model}: Gemini HTTP {r.status_code}{detail}: "
                           f"{_api_error_message(r, self.api_key)}",
                           _category(r.status_code), r.status_code, model)
            exc.retry_after = _retry_after(r)   # the quota's own advice, when given
            raise exc
        return self._parse(r.json(), (time.perf_counter() - started) * 1000, model)

    def generate(self, contents: list[dict], system: str | None = None, tools: list[dict] | None = None,
                 json_schema: dict | None = None) -> LLMResponse:
        started = time.perf_counter()
        deadline = started + self.budget_s
        body = self._body(contents, system, tools, json_schema)
        may_drop_optional = bool(self.thinking_level)
        failures: list[str] = []
        last: LLMError | None = None

        for model in self._candidates():
            for attempt in range(self.MAX_ATTEMPTS):
                if time.perf_counter() >= deadline:
                    raise self._give_up(failures, last, budget_spent=True)
                remaining = deadline - time.perf_counter()
                try:
                    response = self._call(model, body, min(self.timeout, remaining), started)
                except LLMError as exc:
                    last = exc
                    if exc.category in FATAL_CATEGORIES:
                        _record_failure(exc)
                        raise
                    if exc.category == "invalid_request":
                        if may_drop_optional:
                            # An optional generationConfig field the model does not accept should
                            # not take the whole call down: retry once without it.
                            may_drop_optional = False
                            self.dropped_optional = True
                            body = self._body(contents, system, tools, json_schema, with_optional=False)
                            continue
                        _record_failure(exc)
                        raise
                    if exc.category == "model_missing":
                        _forget(self.primary, model)
                        break  # another model may work; no point retrying this one
                    if attempt + 1 < self.MAX_ATTEMPTS:
                        wait = getattr(exc, "retry_after", None) or 0.5 * (2 ** attempt)
                        time.sleep(min(wait, max(0.0, deadline - time.perf_counter())))
                    continue
                self.model = model
                _record_success(self.primary, model)
                return response
            if last is not None:
                failures.append(str(last))
        raise self._give_up(failures, last)

    def _give_up(self, failures: list[str], last: LLMError | None, budget_spent: bool = False) -> LLMError:
        tried = "; ".join(failures) or (str(last) if last else "no attempt completed")
        prefix = (f"Gemini time budget of {self.budget_s:.0f}s exhausted"
                  if budget_spent else "All configured Gemini models failed")
        err = LLMError(f"{prefix}: {tried}", last.category if last else "unknown",
                       last.status if last else None, last.model if last else None)
        _record_failure(err)
        return err

    @staticmethod
    def _parse(data: dict, latency_ms: float, model: str = "") -> LLMResponse:
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError("Gemini returned no candidates (possibly blocked)", "blocked", None, model or None)
        parts = (cands[0].get("content") or {}).get("parts") or []
        text_bits = [p["text"] for p in parts if "text" in p and not p.get("thought")]
        calls = [{"name": p["functionCall"]["name"], "args": p["functionCall"].get("args") or {}}
                 for p in parts if "functionCall" in p]
        u = data.get("usageMetadata") or {}
        usage = {"prompt_tokens": u.get("promptTokenCount", 0), "output_tokens": u.get("candidatesTokenCount", 0),
                 "thoughts_tokens": u.get("thoughtsTokenCount", 0), "total_tokens": u.get("totalTokenCount", 0)}
        return LLMResponse(text="".join(text_bits) or None, function_calls=calls, raw_parts=parts,
                           usage=usage, latency_ms=latency_ms, model=model)


class ScriptedLLM:
    """Test double: returns pre-scripted responses in order and records what it was sent."""

    model = "scripted"

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def generate(self, contents, system=None, tools=None, json_schema=None) -> LLMResponse:
        self.requests.append({"contents": contents, "system": system, "tools": tools, "json_schema": json_schema})
        if not self.responses:
            raise LLMError("ScriptedLLM has no more responses", "config")
        return self.responses.pop(0)


def get_llm(settings: Settings | None = None) -> LLMClient | None:
    s = settings or get_settings()
    if s.effective_mode != "llm" or not s.gemini_api_key:
        return None
    fallbacks = [m.strip() for m in s.gemini_fallback_models.split(",") if m.strip()]
    return GeminiClient(
        s.gemini_api_key,
        s.gemini_model,
        s.llm_timeout_s,
        fallback_models=fallbacks,
        temperature=s.gemini_temperature,
        thinking_level=s.gemini_thinking_level,
        budget_s=s.llm_total_budget_s,
    )


def active_model(settings: Settings | None = None) -> str:
    """Return the model that last succeeded, or the configured primary model."""
    s = settings or get_settings()
    return _WORKING_MODEL.get(s.gemini_model, s.gemini_model)
