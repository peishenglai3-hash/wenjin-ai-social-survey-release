"""Versioned, authenticated Open API gateway.

This is intentionally a narrow chat contract.  It discovers only configured
provider capabilities and never accepts a client-supplied key or base URL.
Project context is owner-scoped until collaboration membership reaches the
shared research-artifact stage.
"""

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_provider_registry
from app.api.deps_auth import get_current_profile
from app.config import settings
from app.models.survey import SurveyProject, UserProfile
from app.middleware.request_context import get_request_id
from app.providers.contracts import ProviderError, ProviderRegistry
from app.schemas.open_api import OpenAPIChatRequest, OpenAPIChatResponse, OpenAPIUsage
from app.services.open_api_usage import check_quota, record_usage

router = APIRouter(prefix="/open-api", tags=["open-api"])
logger = logging.getLogger(__name__)


async def _chat_with_bounded_retry(provider, payload: OpenAPIChatRequest):
    """Retry only provider-declared transient failures, with a hard attempt cap."""
    attempts = max(0, min(settings.open_api_retry_attempts, 3))
    for attempt in range(attempts + 1):
        try:
            return await provider.chat(
                [message.model_dump() for message in payload.messages],
                model=payload.model,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
        except ProviderError as exc:
            if not exc.retryable or attempt >= attempts:
                raise
            await asyncio.sleep(min(1.0, settings.open_api_retry_backoff_s * (2**attempt)))


@router.get("/providers")
async def list_provider_capabilities(
    registry: ProviderRegistry = Depends(get_provider_registry),
):
    """Return safe provider capability metadata without credentials or URLs."""
    if not settings.open_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Open API is disabled")
    return {"providers": registry.manifests()}


@router.post("/chat/completions", response_model=OpenAPIChatResponse)
async def create_chat_completion(
    payload: OpenAPIChatRequest,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
    registry: ProviderRegistry = Depends(get_provider_registry),
):
    """Create one normalized chat completion using a server-side provider."""
    if not settings.open_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Open API is disabled")
    if len(payload.messages) > settings.open_api_max_messages:
        raise HTTPException(status_code=413, detail="Too many messages")
    if sum(len(message.content) for message in payload.messages) > settings.open_api_max_input_chars:
        raise HTTPException(status_code=413, detail="Input content exceeds deployment limit")
    if payload.max_tokens > settings.open_api_max_tokens:
        raise HTTPException(status_code=413, detail="max_tokens exceeds deployment limit")

    if payload.project_id is not None:
        result = await db.execute(
            select(SurveyProject).where(
                SurveyProject.id == payload.project_id,
                SurveyProject.profile_id == profile.id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    _, used_tokens = await check_quota(db, profile.id, payload.max_tokens)
    try:
        provider = registry.get(payload.provider)
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    selected_model = payload.model or provider.manifest.default_model
    request_id = get_request_id()
    try:
        result = await _chat_with_bounded_retry(provider, payload)
    except ProviderError as exc:
        try:
            await record_usage(
                db,
                profile_id=profile.id,
                request_id=request_id,
                provider=provider.manifest.id,
                model=selected_model,
                success=False,
                error_category=exc.category,
            )
        except Exception:
            logger.exception("Failed to record Open API provider failure")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.category in {"provider_unavailable", "timeout", "upstream_unavailable"}
            else status.HTTP_502_BAD_GATEWAY,
            detail=exc.detail,
        ) from exc

    await record_usage(
        db,
        profile_id=profile.id,
        request_id=request_id,
        provider=result.provider,
        model=result.model,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
        total_tokens=result.usage.total_tokens,
    )

    return OpenAPIChatResponse(
        id=f"chatcmpl_{uuid4().hex}",
        request_id=request_id,
        provider=result.provider,
        model=result.model,
        content=result.content,
        usage=OpenAPIUsage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
        quota_remaining_tokens=max(
            0,
            settings.open_api_daily_token_quota
            - used_tokens
            - result.usage.total_tokens,
        ),
    )

