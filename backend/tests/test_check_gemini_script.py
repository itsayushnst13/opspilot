"""The live-check script's helpers: model filtering and key redaction (no network)."""
import importlib.util
from pathlib import Path

import httpx

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_gemini.py"
spec = importlib.util.spec_from_file_location("check_gemini", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_only_models_supporting_generate_content_are_listed():
    body = {"models": [
        {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/embed-only", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-b", "supportedGenerationMethods": ["generateContent"]},
    ]}
    names, error = check.list_models("K", 5, _client(lambda r: httpx.Response(200, json=body)))
    assert names == ["gemini-a", "gemini-b"] and error is None


def test_http_and_network_errors_are_reported_without_the_key():
    def failing(req):
        raise httpx.ConnectError("refused for SECRET", request=req)

    names, error = check.list_models("SECRET", 5, _client(failing))
    assert names == [] and error.startswith("network") and "SECRET" not in error

    body = {"error": {"code": 403, "message": "API key not valid for SECRET"}}
    names, error = check.list_models("SECRET", 5, _client(lambda r: httpx.Response(403, json=body)))
    assert names == [] and error.startswith("HTTP 403") and "SECRET" not in error


def test_redact_removes_the_key():
    assert check.redact("call failed with KEY123", "KEY123") == "call failed with [REDACTED]"
