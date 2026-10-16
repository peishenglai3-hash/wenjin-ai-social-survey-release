"""Dependency injection for API routers."""

import os
from functools import lru_cache

from app.config import settings
from app.core.database import get_db  # noqa: F401 — re-export for routers
from app.services.ai import AIService
from app.services.vision_qwen import QwenVisionService
from app.providers import DashScopeProvider, FakeProvider, OpenAICompatibleProvider, ProviderRegistry


@lru_cache
def get_ai_service() -> AIService:
    """Primary AI service — DeepSeek V4 for reasoning-heavy tasks
    (topic design, questionnaire, methodology, analysis, export, guidance, lessons).

    Lightweight realtime tasks (hints, summarization, memory extraction) are routed
    to the realtime provider (Hunyuan Turbo by default) when configured.
    """
    return AIService(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        realtime_api_key=settings.hunyuan_api_key if settings.hunyuan_enabled else "",
        realtime_base_url=settings.hunyuan_base_url if settings.hunyuan_enabled else "",
        realtime_model=settings.hunyuan_model if settings.hunyuan_enabled else "",
        # Cross-provider fallback: Qwen → Volcano → Hunyuan when DeepSeek unavailable
        fallback_qwen_key=settings.qwen_api_key,
        fallback_qwen_base=settings.qwen_base_url,
        fallback_qwen_model="qwen-max",
        fallback_volcano_key=settings.volcano_api_key,
        fallback_volcano_base=settings.volcano_base_url,
        fallback_volcano_model=settings.volcano_emotion_model,
    )


@lru_cache
def get_vision_service():
    """Vision AI service — Qwen-VL via DashScope native multimodal API.
    Returns QwenVisionService if QWEN_API_KEY is set, else falls back to DeepSeek text-only."""
    if settings.qwen_api_key:
        return QwenVisionService(
            api_key=settings.qwen_api_key,
            model=settings.qwen_vision_model,
        )
    # Fallback: return DeepSeek AIService for text-only analysis
    return get_ai_service()


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    """Build the allow-listed provider adapters from backend-only settings.

    The registry deliberately omits unconfigured providers from selection while
    retaining safe capability metadata for discovery.  No credential is ever
    returned from this dependency or serialized by the API.
    """
    providers = [
        OpenAICompatibleProvider(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        ),
        DashScopeProvider(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.qwen_model,
        ),
    ]
    if settings.open_api_fake_enabled:
        providers.append(FakeProvider())
    return ProviderRegistry(providers)


def ensure_upload_dir() -> str:
    """Ensure the file upload temp directory exists."""
    path = settings.upload_dir
    os.makedirs(path, exist_ok=True)
    return path
