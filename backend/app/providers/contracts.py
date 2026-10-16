"""Small, provider-neutral contracts for the Open API ecosystem.

This module intentionally contains no provider SDK imports.  It is the stable
boundary used by the API gateway and by deterministic tests.  Provider keys and
base URLs live only inside concrete server-side adapters.
"""

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Protocol, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


@dataclass(frozen=True)
class ProviderUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ProviderResponse:
    provider: str
    model: str
    content: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)


@dataclass(frozen=True)
class ProviderManifest:
    """Safe discovery metadata; never include credentials or private URLs."""

    id: str
    label: str
    configured: bool
    capabilities: tuple[str, ...]
    default_model: str

    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "configured": self.configured,
            "capabilities": list(self.capabilities),
            "default_model": self.default_model,
        }


class ProviderError(RuntimeError):
    """Safe, category-bearing provider failure.

    ``detail`` is deliberately suitable for an API response.  Concrete
    adapters may log an internal exception separately, but must not put it in
    this object or return it to a caller.
    """

    def __init__(self, category: str, detail: str, *, retryable: bool = False):
        super().__init__(detail)
        self.category = category
        self.detail = detail
        self.retryable = retryable


class ChatProvider(Protocol):
    manifest: ProviderManifest

    async def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        """Return one deterministic, normalized chat response."""

    async def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Yield normalized text chunks without provider-specific SSE data."""

    async def health(self) -> bool:
        """Return availability without exposing an upstream response body."""


class ProviderRegistry:
    """Explicit allow-list of server-configured providers."""

    def __init__(self, providers: Iterable[ChatProvider] = ()):
        self._providers = {provider.manifest.id: provider for provider in providers}

    def get(self, provider_id: str | None = None) -> ChatProvider:
        if provider_id:
            provider = self._providers.get(provider_id)
            if provider is None or not provider.manifest.configured:
                raise ProviderError("provider_unavailable", "Requested provider is not configured")
            return provider
        for provider in self._providers.values():
            if provider.manifest.configured:
                return provider
        raise ProviderError("provider_unavailable", "No AI provider is configured on the server")

    def manifests(self) -> list[dict]:
        return [provider.manifest.public_dict() for provider in self._providers.values()]

