"""Provider isolation and Gemini wire-format checks; no real keys or API calls."""
import httpx
import pytest
from src.ai.client import AIClient, AIError
from src.extraction.service import ExtractionResponse


@pytest.mark.parametrize("provider,model,url", [
    ("gemini", "gemini-3.8-flash", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
    ("openrouter", "openrouter/free", "https://openrouter.ai/api/v1/chat/completions"),
    ("openai", "configured-test-model", "https://api.openai.com/v1/chat/completions"),
])
def test_provider_uses_only_its_own_key_and_endpoint(monkeypatch, provider, model, url):
    for name in ("gemini", "openrouter", "openai"):
        monkeypatch.setenv(name.upper() + "_API_KEY", name + "-fake-key")
    monkeypatch.setenv("AI_PROVIDER", provider)
    monkeypatch.setenv(provider.upper() + "_MODEL", model)
    monkeypatch.setenv("AI_RESPONSE_FORMAT", "json_schema")
    captured = {}
    def respond(self, request_url, **kwargs):
        captured.update(kwargs)
        captured["url"] = request_url
        return httpx.Response(200, json={"model": model, "choices": [{"finish_reason": "stop", "message": {"content": '{"fields": []}'}}],
                                        "usage": {"prompt_tokens": 12, "completion_tokens": 4}})
    monkeypatch.setattr(httpx.Client, "post", respond)
    client = AIClient()
    assert client.request(ExtractionResponse, "Extract JSON.", {}, "extraction").fields == []
    assert captured["url"] == url
    assert captured["headers"]["Authorization"] == f"Bearer {provider}-fake-key"
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert ("provider" in captured["json"]) == (provider == "openrouter")
    assert ("reasoning_effort" in captured["json"]) == (provider == "gemini")
    assert client.usage[0]["provider"] == provider
    assert "fake-key" not in str(client.usage)


def test_gemini_missing_key_does_not_reuse_openrouter_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "other-provider-fake-key")
    with pytest.raises(AIError, match="GEMINI_API_KEY"):
        AIClient()


def test_invalid_response_format_fails_before_network(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("AI_RESPONSE_FORMAT", "plain_text")
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid settings must not send a request")
    monkeypatch.setattr(httpx.Client, "post", forbidden)
    with pytest.raises(AIError, match="AI_RESPONSE_FORMAT"):
        AIClient().request(ExtractionResponse, "Extract JSON.", {}, "extraction")


@pytest.mark.parametrize("status,match", [(403, "API access was denied"), (429, "quota")])
def test_gemini_quota_and_access_errors_are_actionable(monkeypatch, status, match):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("AI_RESPONSE_FORMAT", "json_schema")
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: httpx.Response(status, json={"error": "private details"}))
    client = AIClient()
    with pytest.raises(AIError, match=match) as exc:
        client.request(ExtractionResponse, "Extract JSON.", {}, "extraction")
    assert "private details" not in str(exc.value)
    assert client.usage[0]["success"] is False
