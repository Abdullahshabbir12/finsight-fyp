"""Small Gemini/OpenRouter/OpenAI client. Keys never enter saved runs or errors."""
import json
import os
from time import perf_counter, sleep
from typing import TypeVar
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-3.8-flash"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "openrouter/free"),
    "openai": ("https://api.openai.com/v1/chat/completions", ""),
}


class AIError(ValueError):
    """A retryable, user-facing AI failure."""


class AIOutputRejected(AIError):
    """The model answered, but its output failed a check. Re-asking with the reason often fixes it."""


def provider_retry_seconds(response: httpx.Response) -> float | None:
    """The provider's requested delay, from Retry-After or Gemini's retryDelay (e.g. "53779s")."""
    try:
        if response.headers.get("retry-after"):
            return float(response.headers["retry-after"])
        body = response.json()
        body = body[0] if isinstance(body, list) and body else body
        for detail in body.get("error", {}).get("details", []):
            if str(detail.get("retryDelay", "")).endswith("s"):
                return float(detail["retryDelay"][:-1])
    except (ValueError, AttributeError, TypeError):
        pass
    return None


def rate_limit_wait(response: httpx.Response) -> float | None:
    """Seconds to wait before one retry after HTTP 429, or None when the quota will not reset within a minute."""
    delay = provider_retry_seconds(response)
    if delay is None:
        try:
            delay = float(os.getenv("FINSIGHT_RATE_LIMIT_WAIT", "30"))
        except ValueError:
            delay = 30
    return delay if delay <= 60 else None


class AIClient:
    def __init__(self) -> None:
        load_dotenv()
        self.provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
        if self.provider not in PROVIDERS:
            raise AIError("AI_PROVIDER must be gemini, openrouter or openai in .env.")
        self.url, default_model = PROVIDERS[self.provider]
        prefix = self.provider.upper()
        self.key = os.getenv(f"{prefix}_API_KEY", "").strip()
        self.model = os.getenv(f"{prefix}_MODEL", default_model).strip()
        if not self.key or not self.model:
            raise AIError(f"Add {prefix}_API_KEY and {prefix}_MODEL to .env, then restart. You can use the synthetic demo or manual verification without a key.")
        self.usage: list[dict] = []

    def request(self, schema: type[T], system: str, payload: dict, stage: str) -> T:
        start = perf_counter()
        json_schema = schema.model_json_schema()
        mode = os.getenv("AI_RESPONSE_FORMAT", "json_schema" if self.provider == "gemini" else "json_object")
        if mode not in {"json_object", "json_schema"}:
            raise AIError("AI_RESPONSE_FORMAT must be json_object or json_schema in .env.")
        response_format = {"type": "json_object"}
        if mode == "json_schema":
            def require_all(node):
                if isinstance(node, dict):
                    if node.get("type") == "object" and "properties" in node:
                        node["required"] = list(node["properties"])
                        node["additionalProperties"] = False
                    node.pop("default", None)
                    for v in node.values():
                        require_all(v)
                elif isinstance(node, list):
                    for v in node:
                        require_all(v)
            require_all(json_schema)
            response_format = {"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": True, "schema": json_schema}}
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\nReturn only one JSON object matching this schema:\n" + json.dumps(json_schema)},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            "response_format": response_format,
            "max_tokens": 7000,
        }
        if self.provider == "openrouter":
            body["provider"] = {"require_parameters": True}
        elif self.provider == "gemini":
            # Leave more of the output budget for the JSON response.
            body["reasoning_effort"] = "low"
        usage = {"stage": stage, "provider": self.provider, "requested_model": self.model,
                 "success": False, "prompt_tokens": None, "completion_tokens": None, "cost": None}
        try:
            with httpx.Client(timeout=httpx.Timeout(90, connect=15)) as client:
                response = client.post(self.url, headers={"Authorization": f"Bearer {self.key}"}, json=body)
                if response.status_code == 429:
                    wait = rate_limit_wait(response)
                    if wait is None:
                        hours = (provider_retry_seconds(response) or 0) / 3600
                        raise AIError(f"The provider's free quota is used up and resets in about {hours:.0f} hours (daily request limit). "
                                      "Completed work is preserved. Retry later, use another provider/model in .env, or use the demo.")
                    # Free tiers also limit requests per minute: wait once, then try again before giving up.
                    sleep(wait)
                    response = client.post(self.url, headers={"Authorization": f"Bearer {self.key}"}, json=body)
                    usage["rate_limit_retry"] = True
            if response.status_code != 200:
                codes = {401: "API key was rejected", 402: "Provider quota or credit is unavailable",
                         403: "API access was denied; check the key's project, API permissions and supported region",
                         429: "Rate limit or free-tier quota reached; check your provider's quota page and wait before retrying",
                         400: "Model rejected the JSON format or request",
                         404: "Model or compatible endpoint is unavailable"}
                raise AIError(codes.get(response.status_code, f"Provider returned HTTP {response.status_code}") + ". Check .env/model settings and retry, or use the demo.")
            data = response.json()
            reported = data.get("usage") or {}
            usage.update({k: reported.get(k) for k in ("prompt_tokens", "completion_tokens", "cost")})
            usage["actual_model"] = data.get("model", self.model)
            choice = data["choices"][0]
            if choice.get("finish_reason") not in {"stop", None}:
                raise AIError("Model output was truncated or stopped. Retry with fewer pages or a different model.")
            result = schema.model_validate_json(choice["message"]["content"])
            usage["success"] = True
            return result
        except (httpx.HTTPError, TimeoutError) as exc:
            raise AIError("Could not reach the AI provider. Check your connection and retry. Your review is preserved.") from exc
        except (ValidationError, KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
            raise AIOutputRejected("The model returned invalid structured JSON. No output was accepted. Retry or select another model.") from exc
        finally:
            usage["seconds"] = perf_counter() - start
            self.usage.append(usage)
