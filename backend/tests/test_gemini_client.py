"""Gemini client policy: model fallback, retries, error categories, budget and status reporting.

Every test uses a mock transport - no API key and no network are involved.
"""
import json

import httpx
import pytest

from app.agents.llm import (GeminiClient, LLMError, active_model, get_llm, llm_status,
                            reset_model_cache)
from app.core.config import Settings


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_model_cache()
    yield
    reset_model_cache()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


def transport(handler):
    return httpx.MockTransport(handler)


def ok(text="hi", usage=None):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    if usage:
        body["usageMetadata"] = usage
    return httpx.Response(200, json=body)


def err(status, message="boom", code_status=None):
    error = {"code": status, "message": message}
    if code_status:
        error["status"] = code_status
    return httpx.Response(status, json={"error": error})


def model_of(req: httpx.Request) -> str:
    return req.url.path.split("/models/")[1].split(":")[0]


def client(handler, model="primary", **kw):
    return GeminiClient("SECRET-KEY", model, transport=transport(handler), **kw)


def call(c):
    return c.generate([{"role": "user", "parts": [{"text": "x"}]}])


# --- happy path -------------------------------------------------------------------------------

def test_primary_model_succeeds_without_touching_fallbacks():
    seen = []
    c = client(lambda r: (seen.append(model_of(r)), ok())[1], fallback_models=["second", "third"])
    assert call(c).text == "hi"
    assert seen == ["primary"] and c.model == "primary"
    assert llm_status()["verified"] is True and llm_status()["model"] == "primary"


def test_usage_metadata_and_model_are_reported():
    usage = {"promptTokenCount": 12, "candidatesTokenCount": 5, "totalTokenCount": 17}
    r = call(client(lambda q: ok("done", usage)))
    assert r.usage == {"prompt_tokens": 12, "output_tokens": 5, "thoughts_tokens": 0, "total_tokens": 17}
    assert r.model == "primary" and r.latency_ms >= 0


def test_explicit_temperature_is_sent_and_default_is_omitted():
    seen = {}

    def handler(req):
        seen.setdefault("bodies", []).append(json.loads(req.content))
        return ok()

    call(client(handler, temperature=0.0))
    call(client(handler))
    assert seen["bodies"][0]["generationConfig"]["temperature"] == 0.0
    assert "generationConfig" not in seen["bodies"][1]


def test_thinking_level_is_sent_only_when_configured():
    seen = {}
    call(client(lambda r: (seen.update(body=json.loads(r.content)), ok())[1], thinking_level="low"))
    assert seen["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


# --- model fallback ---------------------------------------------------------------------------

def test_retired_model_falls_back_and_is_remembered():
    seen = []

    def handler(req):
        m = model_of(req)
        seen.append(m)
        return err(404, f"This model models/{m} is no longer available.") if m == "primary" else ok()

    c = client(handler, fallback_models=["second", "third"])
    assert call(c).text == "hi"
    assert seen == ["primary", "second"] and c.model == "second"

    seen.clear()
    assert call(client(handler, fallback_models=["second", "third"])).model == "second"
    assert seen == ["second"]  # a fresh client starts from the model that worked


def test_400_naming_a_missing_model_also_falls_back():
    seen = []

    def handler(req):
        m = model_of(req)
        seen.append(m)
        return err(400, "Model gemini-x is not found for API version v1beta") if m == "primary" else ok()

    assert call(client(handler, fallback_models=["second"])).text == "hi"
    assert seen == ["primary", "second"]


def test_transient_outage_retries_then_moves_to_the_next_model():
    seen = []

    def handler(req):
        m = model_of(req)
        seen.append(m)
        return err(503, "The model is overloaded.") if m == "primary" else ok()

    assert call(client(handler, fallback_models=["second"])).text == "hi"
    assert seen == ["primary", "primary", "primary", "second"]  # 3 attempts, then the fallback


def test_a_remembered_model_that_was_retired_is_forgotten():
    state = {"second_alive": True}
    seen = []

    def handler(req):
        m = model_of(req)
        seen.append(m)
        if m == "primary":
            return err(404, "no longer available")
        if m == "second" and not state["second_alive"]:
            return err(404, "no longer available")
        return ok()

    assert call(client(handler, fallback_models=["second", "third"])).model == "second"
    state["second_alive"] = False
    seen.clear()
    # "second" is tried first because it worked before, then dropped from the cache
    assert call(client(handler, fallback_models=["second", "third"])).model == "third"
    assert seen == ["second", "primary", "third"]
    seen.clear()
    assert call(client(handler, fallback_models=["second", "third"])).model == "third"
    assert seen == ["third"]


def test_all_models_fail_lists_each_one_and_keeps_the_key_secret():
    c = client(lambda r: err(404, "gone"), fallback_models=["second"])
    with pytest.raises(LLMError) as e:
        call(c)
    assert "primary" in str(e.value) and "second" in str(e.value)
    assert e.value.category == "model_missing" and "SECRET-KEY" not in str(e.value)
    assert llm_status()["verified"] is False and llm_status()["category"] == "model_missing"


# --- failures that must NOT cycle models ------------------------------------------------------

@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_stops_immediately(status):
    seen = []
    c = client(lambda r: (seen.append(model_of(r)), err(status, "API key not valid."))[1],
               fallback_models=["second", "third"])
    with pytest.raises(LLMError) as e:
        call(c)
    assert seen == ["primary"] and e.value.category == "auth" and e.value.status == status


def test_invalid_request_is_not_retried_and_keeps_status_and_message():
    seen = []
    c = client(lambda r: (seen.append(1), err(400, "Invalid JSON payload", "INVALID_ARGUMENT"))[1],
               fallback_models=["second"])
    with pytest.raises(LLMError) as e:
        call(c)
    assert len(seen) == 1 and e.value.category == "invalid_request"
    assert "400" in str(e.value) and "INVALID_ARGUMENT" in str(e.value) and "Invalid JSON payload" in str(e.value)


def test_blocked_response_stops_immediately():
    seen = []
    c = client(lambda r: (seen.append(1), httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))[1],
               fallback_models=["second"])
    with pytest.raises(LLMError) as e:
        call(c)
    assert len(seen) == 1 and e.value.category == "blocked"


def test_rejected_optional_field_is_dropped_once_instead_of_failing():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "thinkingConfig" in body.get("generationConfig", {}):
            return err(400, "Unknown name \"thinkingConfig\"", "INVALID_ARGUMENT")
        return ok()

    assert call(client(handler, thinking_level="low")).text == "hi"
    assert len(bodies) == 2 and "generationConfig" not in bodies[1]


# --- network conditions -----------------------------------------------------------------------

def test_timeout_is_categorised_and_retried_then_falls_back():
    seen = []

    def handler(req):
        m = model_of(req)
        seen.append(m)
        if m == "primary":
            raise httpx.ReadTimeout("timed out", request=req)
        return ok()

    assert call(client(handler, fallback_models=["second"])).text == "hi"
    assert seen == ["primary", "primary", "primary", "second"]


def test_connection_error_everywhere_raises_a_network_error_without_the_key():
    def handler(req):
        raise httpx.ConnectError("refused by SECRET-KEY proxy", request=req)

    with pytest.raises(LLMError) as e:
        call(client(handler))
    assert e.value.category == "network" and "SECRET-KEY" not in str(e.value)


def test_time_budget_stops_a_long_outage(monkeypatch):
    seen = []
    clock = {"t": 0.0}
    monkeypatch.setattr("time.perf_counter", lambda: clock["t"])

    def handler(req):
        seen.append(1)
        clock["t"] += 40.0  # each attempt "takes" 40s
        return err(503, "overloaded")

    with pytest.raises(LLMError) as e:
        call(client(handler, fallback_models=["second", "third"], budget_s=90))
    assert "budget" in str(e.value) and len(seen) < 9  # not 3 models x 3 attempts


# --- wiring -----------------------------------------------------------------------------------

def test_active_model_reports_primary_until_a_model_answers():
    s = Settings(llm_mode="llm", gemini_api_key="k", gemini_model="primary",
                 gemini_fallback_models="second")
    assert active_model(s) == "primary"

    def handler(req):
        return err(404, "gone") if model_of(req) == "primary" else ok()

    call(client(handler, fallback_models=["second"]))
    assert active_model(s) == "second"


def test_get_llm_parses_configuration_and_returns_none_without_a_key():
    s = Settings(llm_mode="llm", gemini_api_key="k", gemini_model="m",
                 gemini_fallback_models=" a , b ,", gemini_temperature=0.2,
                 gemini_thinking_level="low", llm_total_budget_s=12, llm_timeout_s=7)
    c = get_llm(s)
    assert c.primary == "m" and c.fallbacks == ["a", "b"]
    assert c.temperature == 0.2 and c.thinking_level == "low"
    assert c.budget_s == 12 and c.timeout == 7
    assert get_llm(Settings(llm_mode="rules", gemini_api_key="k")) is None
    assert get_llm(Settings(llm_mode="auto", gemini_api_key=None)) is None


def test_metrics_llm_block_separates_configured_from_verified():
    from app.api.metrics import _llm_block

    rules = Settings(llm_mode="rules", gemini_api_key="k")
    assert _llm_block(rules) == {"configured": False, "verified": False, "model": None,
                                 "last_error": None, "category": None}

    s = Settings(llm_mode="llm", gemini_api_key="k", gemini_model="primary")
    block = _llm_block(s)
    assert block["configured"] is True and block["verified"] is False and block["model"] == "primary"

    with pytest.raises(LLMError):
        call(client(lambda r: err(403, "API key not valid."), fallback_models=[]))
    block = _llm_block(s)
    assert block["configured"] is True and block["verified"] is False and block["category"] == "auth"
    assert "SECRET-KEY" not in (block["last_error"] or "")


def test_a_dead_remembered_model_is_not_still_reported_as_active():
    s = Settings(llm_mode="llm", gemini_api_key="k", gemini_model="primary",
                 gemini_fallback_models="second")

    def working(req):
        return err(404, "gone") if model_of(req) == "primary" else ok()

    call(client(working, fallback_models=["second"]))
    assert active_model(s) == "second"

    with pytest.raises(LLMError):
        call(client(lambda r: err(404, "gone"), fallback_models=["second"]))
    assert active_model(s) == "primary"  # the dead model was forgotten, not still advertised


def test_thinking_tokens_are_reported_and_a_dropped_field_is_visible():
    usage = {"promptTokenCount": 8, "candidatesTokenCount": 1, "thoughtsTokenCount": 85, "totalTokenCount": 94}

    r = call(client(lambda q: ok("ok", usage)))
    assert r.usage["thoughts_tokens"] == 85 and r.usage["total_tokens"] == 94

    def rejects_thinking(req):
        if "thinkingConfig" in json.loads(req.content).get("generationConfig", {}):
            return err(400, 'Unknown name "thinkingConfig"', "INVALID_ARGUMENT")
        return ok("ok", usage)

    c = client(rejects_thinking, thinking_level="minimal")
    assert c.dropped_optional is False
    call(c)
    assert c.dropped_optional is True  # the script reports this so a silent drop is never missed


def test_embedder_choice_is_explicit_and_a_quota_error_does_not_kill_a_run():
    import httpx as _httpx
    from app.rag.embed import EmbeddingError, GeminiEmbedder, HashingEmbedder, get_embedder
    from app.tools.kb import SearchKBArgs, search_knowledge_base
    from app.tools.pricing_engine import ToolError

    # "hashing" wins even when a key is present; "gemini" works without llm mode
    assert isinstance(get_embedder(Settings(gemini_api_key="k", llm_mode="llm", embedder="hashing")),
                      HashingEmbedder)
    assert isinstance(get_embedder(Settings(gemini_api_key="k", llm_mode="rules", embedder="gemini")),
                      GeminiEmbedder)

    # the API's own retryDelay is honoured instead of a fixed half second
    body = {"error": {"code": 429, "message": "quota",
                      "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]}}
    assert GeminiEmbedder._retry_after(_httpx.Response(429, json=body)) == 7.0

    class Broken:
        name = "broken"

        def embed_query(self, text):
            raise EmbeddingError("Gemini returned 429")

    import app.tools.kb as kb_mod
    original = kb_mod.get_embedder
    kb_mod.get_embedder = lambda *a, **k: Broken()
    try:
        with pytest.raises(ToolError) as e:
            search_knowledge_base(None, SearchKBArgs(query="x"))
    finally:
        kb_mod.get_embedder = original
    assert "Knowledge base unavailable" in str(e.value) and "429" in str(e.value)


def test_registry_records_an_unexpected_tool_error_instead_of_crashing():
    """A tool raising something other than ToolError must be recorded, not propagated."""
    from dataclasses import replace

    from app.tools.registry import TOOLS, ToolRegistry

    def boom(db, a):
        raise RuntimeError("upstream exploded")

    calls = []
    reg = ToolRegistry(db=None, recorder=calls.append)
    saved = TOOLS["search_product"]
    TOOLS["search_product"] = replace(saved, fn=boom)
    try:
        out = reg.call("search_product", {"query": "x"})
    finally:
        TOOLS["search_product"] = saved
    assert "upstream exploded" in out["error"] and "RuntimeError" in out["error"]
    assert calls[-1]["ok"] is False and calls[-1]["tool"] == "search_product"


def test_rate_limit_waits_as_long_as_the_api_asks():
    slept = []
    body = {"error": {"code": 429, "message": "quota",
                      "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "11s"}]}}
    seen = []

    def handler(req):
        seen.append(1)
        return httpx.Response(429, json=body) if len(seen) < 2 else ok()

    import time as _time
    real = _time.sleep
    _time.sleep = lambda s: slept.append(s)
    try:
        assert call(client(handler)).text == "hi"
    finally:
        _time.sleep = real
    assert slept == [11.0]  # not the blind 0.5 s backoff


def test_report_says_so_when_no_run_reached_the_model():
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from evals.report import llm_usage_banner

    u = {"configured_mode": "llm", "rfq_runs": 30, "runs_that_used_the_model": 0,
         "runs_that_fell_back_to_rules": 30, "extraction_method": {"rules": 30}, "llm_calls_total": 0}
    assert "NOT language-model numbers" in "".join(llm_usage_banner(u)) and "0 of 30" in "".join(llm_usage_banner(u))

    u.update(runs_that_used_the_model=25, runs_that_fell_back_to_rules=5)
    assert "Partial LLM run" in "".join(llm_usage_banner(u))

    u.update(runs_that_used_the_model=30, runs_that_fell_back_to_rules=0)
    text = "".join(llm_usage_banner(u))
    assert "NOT language-model numbers" not in text and "Partial LLM run" not in text
    assert "Which path actually ran" in text  # the counts are always shown

    u["configured_mode"] = "rules"
    assert "NOT language-model numbers" not in "".join(llm_usage_banner(u))
