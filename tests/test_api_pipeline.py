"""Mock HTTP and live pipeline behavior without keys, network or spending."""
import json
import httpx
import pytest
from src.ai.client import AIClient, AIError
from src.ai.council import run_council, demo_analyst
from src.ai.synthesis import run_synthesis, demo_synthesis
from src.ai.council import reference_registry
from src.demo import demo_run
from src.extraction.service import ExtractionResponse, extract_fields
from src.models import FinancialField
from tests.test_validation import reviewed_demo


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/free")
    monkeypatch.setenv("FINSIGHT_RATE_LIMIT_WAIT", "0")
    return AIClient()


def mock_response(monkeypatch, status, data):
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: httpx.Response(status, json=data))


@pytest.mark.parametrize("status", [400, 401, 402, 404, 429, 500])
def test_api_errors_are_safe_and_recorded(client, monkeypatch, status):
    mock_response(monkeypatch, status, {"error": "secret-provider-debug"})
    with pytest.raises(AIError) as exc:
        client.request(ExtractionResponse, "system", {}, "test")
    assert "secret-provider-debug" not in str(exc.value)
    assert len(client.usage) == 1 and not client.usage[0]["success"]


def test_invalid_json_and_valid_json(client, monkeypatch):
    mock_response(monkeypatch, 200, {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]})
    with pytest.raises(AIError, match="invalid structured"):
        client.request(ExtractionResponse, "system", {}, "test")
    mock_response(monkeypatch, 200, {"choices": [{"finish_reason": "stop", "message": {"content": '{"fields": []}'}}],
                                    "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "model": "actual/free"})
    result = client.request(ExtractionResponse, "system", {}, "test")
    assert result.fields == []
    assert client.usage[-1]["actual_model"] == "actual/free"
    assert client.usage[-1]["prompt_tokens"] == 100


def test_timeout_is_safe(client, monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("internal secret details")
    monkeypatch.setattr(httpx.Client, "post", fail)
    with pytest.raises(AIError, match="connection"):
        client.request(ExtractionResponse, "system", {}, "test")


def test_no_key_has_setup_instructions(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    with pytest.raises(AIError, match=".env"):
        AIClient()


def test_extraction_partial_failure_preserves_evidence_and_accounts_usage():
    run = demo_run()
    class Fake:
        usage = []
        count = 0
        def request(self, *args):
            self.count += 1
            self.usage.append({"stage": "extraction", "success": self.count == 1})
            if self.count == 2:
                raise AIError("Rate limit reached")
            return ExtractionResponse(fields=[{"field_name": "revenue", "reporting_year": 2025, "raw_value": "1000",
                "unit": "PKR million", "source_page": 1, "source_text": run.fields[0].source_text,
                "confidence": .9, "statement_basis": "consolidated"}])
    extract_fields(run, [1, 2, 3], Fake())
    assert len(run.fields) == 27
    assert run.fields[0].normalized_value == 1000000000
    assert run.fields[1].normalized_value is None
    assert any("Rate limit" in w for w in run.warnings)
    assert len(run.usage) == 2


def test_council_resume_and_live_synthesis():
    run = reviewed_demo()
    run.is_demo = False
    class Fake:
        def __init__(self):
            self.usage = []
            self.count = 0
            self.fail = True
        def request(self, schema, system, payload, stage):
            self.count += 1
            self.usage.append({"stage": stage, "success": True})
            if stage == "Credit Risk Analyst" and self.fail:
                self.fail = False
                raise AIError("Rate limited")
            if stage == "synthesis":
                return demo_synthesis(run, reference_registry(run))
            return demo_analyst(run, stage)
    client = Fake()
    with pytest.raises(AIError):
        run_council(run, client)
    assert list(run.analysts) == ["Fundamental Analyst"]
    run_council(run, client)
    assert len(run.analysts) == 4
    assert client.count == 5
    run_synthesis(run, client)
    assert run.synthesis and len(run.usage) == 6


def test_malformed_envelope_is_graceful(client, monkeypatch):
    mock_response(monkeypatch, 200, [])
    with pytest.raises(AIError, match="invalid structured"):
        client.request(ExtractionResponse, "system", {}, "test")


def test_strict_extraction_schema_has_defined_fields(client, monkeypatch):
    monkeypatch.setenv("AI_RESPONSE_FORMAT", "json_schema")
    captured = {}
    def response(*args, **kwargs):
        captured.update(kwargs["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"fields": []}'}, "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx.Client, "post", response)
    client.request(ExtractionResponse, "system", {}, "test")
    schema = captured["response_format"]["json_schema"]["schema"]
    assert "Candidate" in schema["$defs"]
    assert schema["$defs"]["Candidate"]["additionalProperties"] is False
    assert set(schema["$defs"]["Candidate"]["required"]) == set(schema["$defs"]["Candidate"]["properties"])


def test_rate_limit_waits_once_then_succeeds(client, monkeypatch):
    replies = iter([httpx.Response(429, json={}),
                    httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"fields": []}'}}]})])
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: next(replies))
    assert client.request(ExtractionResponse, "system", {}, "test").fields == []
    assert client.usage[-1]["success"] and client.usage[-1]["rate_limit_retry"]


def test_daily_quota_is_reported_without_waiting(client, monkeypatch):
    body = {"error": {"details": [{"retryDelay": "53779s"}]}}
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return httpx.Response(429, json=body)
    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(AIError, match="resets in about 15 hours"):
        client.request(ExtractionResponse, "system", {}, "test")
    assert len(calls) == 1
