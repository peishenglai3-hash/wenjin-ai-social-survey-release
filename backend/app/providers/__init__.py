"""Provider adapters used by the versioned Open API surface.

The legacy :mod:`app.services.ai` service remains available for the original
single-user routes.  New integrations should depend on the small contracts in
this package so that provider credentials stay server-side and capabilities
can be advertised without exposing configuration secrets.
"""

from app.providers.contracts import (
    ChatMessage,
    ChatProvider,
    ProviderError,
    ProviderManifest,
    ProviderRegistry,
    ProviderResponse,
    ProviderUsage,
)
from app.providers.fake import FakeProvider
from app.providers.openai_compatible import DashScopeProvider, OpenAICompatibleProvider

__all__ = [
    "ChatMessage",
    "ChatProvider",
    "DashScopeProvider",
    "FakeProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "ProviderManifest",
    "ProviderRegistry",
    "ProviderResponse",
    "ProviderUsage",
]
