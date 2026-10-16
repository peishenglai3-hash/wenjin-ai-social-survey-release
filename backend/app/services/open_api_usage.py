"""Quota accounting for the versioned Open API gateway."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.open_api import OpenAPIUsageRecord


def _cutoff() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)


async def check_quota(
    db: AsyncSession, profile_id: int, requested_tokens: int
) -> tuple[int, int]:
    """Return (used_requests, used_tokens), failing closed over the daily budget."""
    result = await db.execute(
        select(
            func.count(OpenAPIUsageRecord.id),
            func.coalesce(func.sum(OpenAPIUsageRecord.total_tokens), 0),
        ).where(
            OpenAPIUsageRecord.profile_id == profile_id,
            OpenAPIUsageRecord.created_at >= _cutoff(),
        )
    )
    used_requests, used_tokens = result.one()
    used_requests = int(used_requests or 0)
    used_tokens = int(used_tokens or 0)
    if used_requests >= settings.open_api_daily_request_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Open API daily request quota exceeded",
            headers={"Retry-After": "3600"},
        )
    if used_tokens + requested_tokens > settings.open_api_daily_token_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Open API daily token quota exceeded",
            headers={"Retry-After": "3600"},
        )
    return used_requests, used_tokens


async def record_usage(
    db: AsyncSession,
    *,
    profile_id: int,
    request_id: str | None,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    success: bool = True,
    error_category: str | None = None,
) -> OpenAPIUsageRecord:
    """Persist only operational metadata; prompts and outputs never enter this table."""
    record = OpenAPIUsageRecord(
        profile_id=profile_id,
        request_id=request_id,
        provider=provider[:64],
        model=model[:128],
        prompt_tokens=max(0, int(prompt_tokens)),
        completion_tokens=max(0, int(completion_tokens)),
        total_tokens=max(0, int(total_tokens)),
        status="success" if success else "failed",
        error_category=error_category[:50] if error_category else None,
    )
    db.add(record)
    await db.commit()
    return record
