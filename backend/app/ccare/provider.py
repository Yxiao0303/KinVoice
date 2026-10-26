"""OpenAI-compatible wire protocol, without silent mock responses or retries."""
from dataclasses import dataclass
import httpx
import re

from .config import Settings


class ProviderUnavailable(Exception):
    def __init__(self, code="provider_unavailable", *, usage=None, model=None, http_status=None):
        super().__init__()
        self.code = code
        self.usage, self.model = usage, model
        self.http_status = http_status


@dataclass
class Completion:
    text: str
    usage: dict | None = None
    model: str | None = None
    http_status: int | None = None


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
        usage, returned_model = None, None
        http_status = None
        try:
            async with httpx.AsyncClient(timeout=c.call_timeout, follow_redirects=False, trust_env=True) as client:
                async with client.stream(
                    "POST", c.api_base.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + c.api_key},
                    json=payload,
                ) as response:
                    http_status = response.status_code
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 128000:
                            raise ProviderUnavailable("response_too_large")
                        chunks.append(chunk)
                    import json
                    data = json.loads(b"".join(chunks))
            raw_usage = data.get("usage")
            usage = None
            if isinstance(raw_usage, dict):
                usage = {key: raw_usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
                         if type(raw_usage.get(key)) is int and raw_usage[key] >= 0}
                details = raw_usage.get("completion_tokens_details")
                if isinstance(details, dict) and type(details.get("reasoning_tokens")) is int and details["reasoning_tokens"] >= 0:
                    usage["completion_tokens_details"] = {"reasoning_tokens": details["reasoning_tokens"]}
                usage = usage or None
            candidate_model = data.get("model")
            returned_model = candidate_model if isinstance(candidate_model, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", candidate_model) else None

            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip() or len(content) > 12000:
                raise ProviderUnavailable("invalid_response", usage=usage, model=returned_model)
            finish = choice.get("finish_reason")
            if finish != "stop" and (c.provider_kind == "deepseek" or finish is not None):
                raise ProviderUnavailable("incomplete_output", usage=usage, model=returned_model)
            return Completion(content, usage, returned_model, http_status)
        except httpx.HTTPStatusError as exc:
            code = {401: "invalid_key", 402: "insufficient_balance", 429: "rate_limited", 400: "invalid_request", 422: "invalid_request"}.get(exc.response.status_code, "provider_http_error")
            raise ProviderUnavailable(code, http_status=http_status) from None
        except ProviderUnavailable as exc:
            exc.http_status = http_status
            raise
        except httpx.TimeoutException:
            raise ProviderUnavailable("provider_timeout", http_status=http_status) from None
        except httpx.HTTPError:
            raise ProviderUnavailable("connection_error", http_status=http_status) from None
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            # Never include provider bodies, credentials or user text in exceptions/logs.
            raise ProviderUnavailable("invalid_response", usage=usage, model=returned_model, http_status=http_status) from None
