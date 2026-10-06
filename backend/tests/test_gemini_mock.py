"""Gemini REST client + embedder against a mock transport. NOT a live-API test."""
import json

import httpx
import pytest

from app.agents.llm import GeminiClient, LLMError
from app.rag.embed import EmbeddingError, GeminiEmbedder


def transport(handler):
    return httpx.MockTransport(handler)


def test_generate_sends_key_in_header_and_parses_function_call():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "search_product", "args": {"query": "X01"}}}]}}],
            "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 3, "totalTokenCount": 14}})

    c = GeminiClient("SECRET", "gemini-test", transport=transport(handler))
    r = c.generate([{"role": "user", "parts": [{"text": "hi"}]}], system="sys", tools=[{"name": "search_product"}])
    assert r.function_calls == [{"name": "search_product", "args": {"query": "X01"}}]
    assert r.usage["prompt_tokens"] == 11
    assert "SECRET" not in seen["url"] and seen["key"] == "SECRET"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert seen["body"]["tools"][0]["functionDeclarations"][0]["name"] == "search_product"
    assert seen["body"]["generationConfig"]["temperature"] == 0.0


def test_json_schema_mode_and_text_parse():
    def handler(req):
        body = json.loads(req.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "{\"a\": 1}"}]}}]})

    c = GeminiClient("k", "m", transport=transport(handler))
    assert c.generate([{"role": "user", "parts": [{"text": "x"}]}], json_schema={"type": "object"}).text == '{"a": 1}'


def test_retries_then_raises_without_leaking_key(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"error": "busy"})

    c = GeminiClient("SECRET", "m", transport=transport(handler))
    with pytest.raises(LLMError) as e:
        c.generate([{"role": "user", "parts": [{"text": "x"}]}])
    assert len(calls) == 3 and "SECRET" not in str(e.value)


def test_client_error_and_blocked_response():
    c = GeminiClient("k", "m", transport=transport(lambda r: httpx.Response(400, json={"error": "bad"})))
    with pytest.raises(LLMError):
        c.generate([{"role": "user", "parts": [{"text": "x"}]}])
    c = GeminiClient("k", "m", transport=transport(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})))
    with pytest.raises(LLMError):
        c.generate([{"role": "user", "parts": [{"text": "x"}]}])


def test_thought_parts_are_not_returned_as_text():
    body = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": "answer"}]}}]}
    c = GeminiClient("k", "m", transport=transport(lambda r: httpx.Response(200, json=body)))
    assert c.generate([{"role": "user", "parts": [{"text": "x"}]}]).text == "answer"


def test_embedder_batches_and_normalises():
    sizes = []

    def handler(req):
        reqs = json.loads(req.content)["requests"]
        sizes.append(len(reqs))
        assert reqs[0]["outputDimensionality"] == 4 and reqs[0]["taskType"] == "RETRIEVAL_DOCUMENT"
        return httpx.Response(200, json={"embeddings": [{"values": [3.0, 4.0, 0.0, 0.0]} for _ in reqs]})

    e = GeminiEmbedder("k", "gemini-embedding-001", dim=4, transport=transport(handler))
    vecs = e.embed_documents([f"t{i}" for i in range(120)])
    assert sizes == [50, 50, 20] and len(vecs) == 120
    assert vecs[0] == pytest.approx([0.6, 0.8, 0, 0])


def test_embedder_count_mismatch_is_an_error():
    e = GeminiEmbedder("k", "m", dim=4, transport=transport(lambda r: httpx.Response(200, json={"embeddings": []})))
    with pytest.raises(EmbeddingError):
        e.embed_query("x")
