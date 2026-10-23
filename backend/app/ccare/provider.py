"""OpenAI-compatible wire protocol, without silent mock responses or retries."""
from dataclasses import dataclass
import httpx

from .config import Settings


class ProviderUnavailable(Exception):
    def __init__(self, code="provider_unavailable"):
        super().__init__()
        self.code = code


@dataclass
class Completion:
    text: str
    usage: dict | None = None
    model: str | None = None


class RemoteProvider:
    def __init__(self, config: Settings):
        self.config = config

    async def complete(self, messages: list[dict], *, temperature: float, max_tokens: int, json_mode: bool = False) -> Completion:
        c = self.config
        payload = {"model": c.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if c.provider_kind == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with httpx.AsyncClient(timeout=c.call_timeout, follow_redirects=False, trust_env=False) as client:
                async with client.stream(
                    "POST", c.api_base.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + c.api_key},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 128000:
                            raise ProviderUnavailable("response_too_large")
                        chunks.append(chunk)
                    import json
                    data = json.loads(b"".join(chunks))
            choice = data["choices"][0]
            if choice.get("finish_reason") not in (None, "stop"):
                raise ProviderUnavailable("incomplete_output")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip() or len(content) > 12000:
                raise ProviderUnavailable("invalid_response")
            raw_usage = data.get("usage")
            usage = None
            if isinstance(raw_usage, dict):
                usage = {key: raw_usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
                         if type(raw_usage.get(key)) is int and raw_usage[key] >= 0}
                usage = usage or None
            returned_model = data.get("model")
            return Completion(content, usage, returned_model if isinstance(returned_model, str) else None)
        except httpx.HTTPStatusError as exc:
            code = {401: "invalid_key", 402: "insufficient_balance", 429: "rate_limited", 400: "invalid_request", 422: "invalid_request"}.get(exc.response.status_code, "provider_http_error")
            raise ProviderUnavailable(code) from None
        except httpx.TimeoutException:
            raise ProviderUnavailable("provider_timeout") from None
        except httpx.HTTPError:
            raise ProviderUnavailable("connection_error") from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            # Never include provider bodies, credentials or user text in exceptions/logs.
            raise ProviderUnavailable("invalid_response") from None
