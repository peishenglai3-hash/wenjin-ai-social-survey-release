"""Deterministic local provider for contract tests and offline development."""

from collections.abc import AsyncIterator, Iterable

from app.providers.contracts import (
    ChatMessage,
    ProviderManifest,
    ProviderResponse,
    ProviderUsage,
)


class FakeProvider:
    """A no-network provider with stable output and configurable chunks."""

    def __init__(
        self,
        response: str = "fake provider response",
        *,
        chunks: tuple[str, ...] | None = None,
        model: str = "wenjin-fake-1",
    ):
        self.response = response
        self.chunks = chunks or (response,)
        self.manifest = ProviderManifest(
            id="fake",
            label="Local fake provider",
            configured=True,
            capabilities=("chat", "stream", "health"),
            default_model=model,
        )

    async def chat(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProviderResponse:
        del messages, temperature, max_tokens
        selected_model = model or self.manifest.default_model
        return ProviderResponse(
            provider=self.manifest.id,
            model=selected_model,
            content=self.response,
            usage=ProviderUsage(total_tokens=1),
        )

    async def chat_stream(
        self,
        messages: Iterable[ChatMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        del messages, model, temperature, max_tokens
        for chunk in self.chunks:
            yield chunk

    async def health(self) -> bool:
        return True

