"""Versioned, authenticated Open API gateway.

This is intentionally a narrow chat contract.  It discovers only configured
provider capabilities and never accepts a client-supplied key or base URL.
Project context is owner-scoped until collaboration membership reaches the
shared research-artifact stage.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_provider_registry
from app.api.deps_auth import get_current_profile
from app.config import settings
from app.models.survey import SurveyProject, UserProfile
from app.providers.contracts import ProviderError, ProviderRegistry
from app.schemas.open_api import OpenAPIChatRequest, OpenAPIChatResponse, OpenAPIUsage

router = APIRouter(prefix="/open-api", tags=["open-api"])


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

    try:
        provider = registry.get(payload.provider)
        result = await provider.chat(
            [message.model_dump() for message in payload.messages],
            model=payload.model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            if exc.category in {"provider_unavailable", "timeout", "upstream_unavailable"}
            else status.HTTP_502_BAD_GATEWAY,
            detail=exc.detail,
        ) from exc

    return OpenAPIChatResponse(
        id=f"chatcmpl_{uuid4().hex}",
        provider=result.provider,
        model=result.model,
        content=result.content,
        usage=OpenAPIUsage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )

