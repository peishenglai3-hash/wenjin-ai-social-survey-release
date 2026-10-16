"""Adapters for OpenAI-compatible HTTP chat APIs.

DashScope's compatible-mode endpoint is intentionally represented as a thin
subclass.  This keeps the gateway contract identical while leaving provider
credentials and endpoint details in server configuration.
"""

import json
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any, Callable

import httpx

from app.providers.contracts import (
    ChatMessage,
    ProviderError,
    ProviderManifest,
    ProviderResponse,
    ProviderUsage,
)

logger = logging.getLogger(__name__)


def _usage(payload: dict[str, Any]) -> ProviderUsage:
    raw = payload.get("usage") or {}
    return ProviderUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        total_tokens=int(raw.get("total_tokens") or 0),
    )


class OpenAICompatibleProvider:
    """Server-side adapter for ``/chat/completions`` and ``/models``."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_id: str = "openai-compatible",
        label: str = "OpenAI-compatible provider",
        timeout_s: float = 60.0,
        client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
    ):
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client_factory = client_factory
        self.manifest = ProviderManifest(
            id=provider_id,
            label=label,
            configured=bool(self._api_key and self._base_url),
            capabilities=("chat", "stream", "health"),
            default_model=model,
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _ensure_configured(self) -> None:
        if not self.manifest.configured:
            raise ProviderError("provider_unavailable", "Provider is not configured")

    @staticmethod
    def _safe_error(response: httpx.Response) -> ProviderError:
        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            return ProviderError(
                "upstream_unavailable",
                "The configured AI provider is temporarily unavailable",
                retryable=True,
            )
        return ProviderError("upstream_rejected", "The configured AI provider rejected the request")

    async def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        self._ensure_configured()
        selected_model = model or self.manifest.default_model
        payload = {
            "model": selected_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            async with self._client_factory(timeout=self._timeout_s) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "AI provider request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("upstream_unavailable", "AI provider connection failed", retryable=True) from exc
        if response.status_code >= 400:
            raise self._safe_error(response)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("invalid_provider_response", "AI provider returned an invalid response") from exc
        return ProviderResponse(
            provider=self.manifest.id,
            model=selected_model,
            content=str(content),
            usage=_usage(data),
        )

    async def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        self._ensure_configured()
        selected_model = model or self.manifest.default_model
        payload = {
            "model": selected_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with self._client_factory(timeout=self._timeout_s) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        raise self._safe_error(response)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            data = json.loads(raw)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                        except (ValueError, KeyError, IndexError, TypeError):
                            logger.debug("Ignoring malformed provider stream chunk")
                            continue
                        if content:
                            yield str(content)
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderError("timeout", "AI provider stream timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError("upstream_unavailable", "AI provider stream failed", retryable=True) from exc

    async def health(self) -> bool:
        if not self.manifest.configured:
            return False
        try:
            async with self._client_factory(timeout=min(self._timeout_s, 5.0)) as client:
                response = await client.get(f"{self._base_url}/models", headers=self._headers())
            return response.status_code == 200
        except (httpx.HTTPError, ProviderError):
            return False


class DashScopeProvider(OpenAICompatibleProvider):
    """DashScope compatible-mode adapter with the same normalized contract."""

    def __init__(self, *, api_key: str, base_url: str, model: str, **kwargs: Any):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider_id="dashscope",
            label="Alibaba DashScope compatible provider",
            **kwargs,
        )

