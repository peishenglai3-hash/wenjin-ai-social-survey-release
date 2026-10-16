"""AI service layer — DeepSeek V4 integration with streaming + model routing.

Includes per-user cost circuit breaker that blocks requests when the user
exceeds their daily or monthly token budget.
"""

import logging
import time
from typing import AsyncGenerator

from fastapi import HTTPException, status
from httpx import AsyncClient

from app.config import settings
from app.middleware.token_logger import get_user_usage, log_token_usage

logger = logging.getLogger(__name__)


class ProviderNotConfiguredError(RuntimeError):
    """Raised when no server-side provider credentials are available."""

# Task → model routing: Pro for complex reasoning, Flash for lightweight tasks
TASK_MODELS = {
    "topic": "deepseek-v4-pro",
    "questionnaire": "deepseek-v4-pro",
    "hints": "deepseek-v4-flash",
    "summarize": "deepseek-v4-flash",
    "analysis": "deepseek-v4-pro",
    "export": "deepseek-v4-pro",
    "image": "deepseek-v4-pro",
    "guidance": "deepseek-v4-pro",
    "lessons": "deepseek-v4-pro",
}

# Tasks that may be routed to the realtime provider (Hunyuan) when configured.
# Controlled by settings.realtime_provider: "hunyuan" routes these to Hunyuan Turbo.
REALTIME_TASKS = {"hints", "summarize", "memory_extraction", "memory_skill_gen"}

TASK_MAX_TOKENS = {
    "topic": 8192,
    "questionnaire": 8192,
    "hints": 1024,
    "summarize": 4096,
    "analysis": 8192,
    "export": 8192,
    "image": 4096,
    "guidance": 6144,
    "lessons": 4096,
    "memory_extraction": 2048,
    "memory_skill_gen": 4096,
}


class AIService:
    """Thin wrapper over AI provider APIs with cost circuit breaker.

    Supports optional secondary 'realtime' provider (e.g. Hunyuan Turbo) for
    low-latency tasks (hints, summarization, memory extraction).  When
    configured, tasks listed in REALTIME_TASKS are routed to the realtime
    provider; all other tasks stay on the primary (DeepSeek) provider.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "deepseek-v4-pro",
        *,
        default_user_id: int | None = None,
        realtime_api_key: str = "",
        realtime_base_url: str = "",
        realtime_model: str = "",
        # Cross-provider fallback chain (tried in order when primary key is unset)
        fallback_qwen_key: str = "",
        fallback_qwen_base: str = "",
        fallback_qwen_model: str = "qwen-max",
        fallback_volcano_key: str = "",
        fallback_volcano_base: str = "",
        fallback_volcano_model: str = "doubao-seed-2-0-pro-260215",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.default_user_id = default_user_id
        self.realtime_api_key = realtime_api_key
        self.realtime_base_url = realtime_base_url.rstrip("/") if realtime_base_url else ""
        self.realtime_model = realtime_model
        # Fallback providers
        self.fb_qwen_key = fallback_qwen_key
        self.fb_qwen_base = fallback_qwen_base.rstrip("/") if fallback_qwen_base else ""
        self.fb_qwen_model = fallback_qwen_model
        self.fb_volcano_key = fallback_volcano_key
        self.fb_volcano_base = fallback_volcano_base.rstrip("/") if fallback_volcano_base else ""
        self.fb_volcano_model = fallback_volcano_model
        self.last_usage: dict = {}

    @property
    def realtime_enabled(self) -> bool:
        return bool(self.realtime_api_key and self.realtime_base_url)

    def _route(self, task: str) -> tuple[str, str, str]:
        """Resolve (api_key, base_url, model) for a given task.

        Routes tasks in REALTIME_TASKS to the realtime provider when configured.
        For all other tasks, tries providers in priority order:
        DeepSeek → Qwen (DashScope) → Volcano (ARK) → Hunyuan (realtime).
        """
        if task in REALTIME_TASKS and self.realtime_enabled:
            return self.realtime_api_key, self.realtime_base_url, self.realtime_model

        # Primary: DeepSeek
        if self.api_key:
            return self.api_key, self.base_url, self._model_for(task)

        # Fallback 1: Qwen (DashScope, OpenAI-compatible)
        if self.fb_qwen_key:
            return self.fb_qwen_key, self.fb_qwen_base, self.fb_qwen_model

        # Fallback 2: Volcano (ARK, OpenAI-compatible)
        if self.fb_volcano_key:
            return self.fb_volcano_key, self.fb_volcano_base, self.fb_volcano_model

        # Fallback 3: Hunyuan (works for general tasks too, not just realtime)
        if self.realtime_enabled:
            return self.realtime_api_key, self.realtime_base_url, self.realtime_model

        raise ProviderNotConfiguredError(
            "No AI provider is configured on the server."
        )

    def _model_for(self, task: str) -> str:
        return TASK_MODELS.get(task, self.model)

    def _max_tokens_for(self, task: str) -> int:
        return TASK_MAX_TOKENS.get(task, 4096)

    def _effective_user_id(self, user_id: int | None) -> int | None:
        """Use the request-scoped profile when callers omit an explicit id."""
        return self.default_user_id if user_id is None else user_id

    def _bounded_max_tokens(self, task: str, requested: int) -> int:
        """Apply the per-task ceiling without silently expanding requests."""
        return min(max(1, int(requested)), self._max_tokens_for(task) if task else 4096)

    def _check_cost_limit(self, user_id: int | None) -> None:
        """Raise 429 if user exceeds daily or monthly token budget."""
        if not settings.cost_limit_enabled or user_id is None:
            return
        daily = get_user_usage(user_id, hours=24.0)
        monthly = get_user_usage(user_id, hours=720.0)
        if daily["total_tokens"] >= settings.cost_limit_tokens_per_user_day:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Daily AI token budget exceeded "
                    f"({daily['total_tokens']:,}/{settings.cost_limit_tokens_per_user_day:,} tokens). "
                    f"Limit resets hourly on a rolling 24h window."
                ),
            )
        if monthly["total_tokens"] >= settings.cost_limit_tokens_per_user_month:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Monthly AI token budget exceeded "
                    f"({monthly['total_tokens']:,}/{settings.cost_limit_tokens_per_user_month:,} tokens). "
                    f"Contact admin to increase limit."
                ),
            )

    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task: str = "",
        user_id: int | None = None,
    ) -> str:
        # Resolve provider + model for this task
        try:
            api_key, base_url, routed_model = self._route(task)
        except ProviderNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        model = model or routed_model
        max_tokens = self._bounded_max_tokens(task, max_tokens)
        user_id = self._effective_user_id(user_id)
        self._check_cost_limit(user_id)
        t0 = time.time()
        try:
            async with AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                if usage:
                    self.last_usage = {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    }
                    log_token_usage(
                        model=model, task=task,
                        prompt_tokens=self.last_usage["prompt_tokens"],
                        completion_tokens=self.last_usage["completion_tokens"],
                        total_tokens=self.last_usage["total_tokens"],
                        user_id=user_id,
                        duration_ms=(time.time() - t0) * 1000,
                    )
                return content
        except HTTPException:
            raise
        except Exception as e:
            log_token_usage(
                model=model, task=task,
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                user_id=user_id,
                duration_ms=(time.time() - t0) * 1000,
                success=False, error=str(e),
            )
            raise

    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        task: str = "",
        user_id: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from the AI provider via SSE."""
        # Resolve provider + model for this task
        try:
            api_key, base_url, routed_model = self._route(task)
        except ProviderNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        model = model or routed_model
        max_tokens = self._bounded_max_tokens(task, max_tokens)
        user_id = self._effective_user_id(user_id)
        self._check_cost_limit(user_id)
        t0 = time.time()
        last_usage_chunk: dict = {}
        try:
            async with AsyncClient(timeout=180) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                import json
                                chunk = json.loads(data)
                                usage = chunk.get("usage")
                                if usage:
                                    last_usage_chunk = {
                                        "prompt_tokens": usage.get("prompt_tokens", 0),
                                        "completion_tokens": usage.get("completion_tokens", 0),
                                        "total_tokens": usage.get("total_tokens", 0),
                                    }
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                logger.debug("Failed to parse streaming SSE chunk", exc_info=True)
                                continue
            if last_usage_chunk:
                self.last_usage = last_usage_chunk
            log_token_usage(
                model=model, task=task,
                prompt_tokens=last_usage_chunk.get("prompt_tokens", 0),
                completion_tokens=last_usage_chunk.get("completion_tokens", 0),
                total_tokens=last_usage_chunk.get("total_tokens", 0),
                user_id=user_id,
                duration_ms=(time.time() - t0) * 1000,
            )
        except HTTPException:
            raise
        except Exception as e:
            log_token_usage(
                model=model, task=task,
                prompt_tokens=0, completion_tokens=0, total_tokens=0,
                user_id=user_id,
                duration_ms=(time.time() - t0) * 1000,
                success=False, error=str(e),
            )
            raise

    async def chat_with_image(
        self,
        text: str,
        image_base64: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        user_id: int | None = None,
    ) -> str:
        """Send a multimodal request with text + image."""
        try:
            api_key, base_url, routed_model = self._route("image")
        except ProviderNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        model = model or routed_model
        user_id = self._effective_user_id(user_id)
        max_tokens = self._bounded_max_tokens("image", max_tokens)
        self._check_cost_limit(user_id)
        try:
            async with AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": text},
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                                    },
                                ],
                            }
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 400:
                    raise VisionNotSupportedError(
                        "The configured AI provider does not support image input. "
                        "Falling back to text-only analysis."
                    )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except VisionNotSupportedError:
            raise
        except HTTPException:
            raise
        except Exception as e:
            if "400" in str(e) or "image_url" in str(e).lower():
                raise VisionNotSupportedError(
                    "Image analysis is not supported by the configured AI provider. "
                    "Configure a vision-capable model or use text descriptions."
                )
            raise

    async def health(self) -> bool:
        """Quick check that the API is reachable and key is valid."""
        try:
            api_key, base_url, _ = self._route("")
            async with AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return resp.status_code == 200
        except ProviderNotConfiguredError:
            return False
        except Exception:
            logger.warning("AI provider health check failed", exc_info=True)
            return False


class VisionNotSupportedError(Exception):
    """Raised when the AI provider doesn't support multimodal/image input."""
    pass
