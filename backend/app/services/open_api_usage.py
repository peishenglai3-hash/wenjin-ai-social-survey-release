"""Quota accounting for the versioned Open API gateway."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.open_api import OpenAPIUsageRecord
from app.models.survey import UserProfile


def _cutoff() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)


_RESERVATION_TTL = timedelta(minutes=10)


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
    record_id: int | None = None,
) -> OpenAPIUsageRecord:
    """Persist only operational metadata; prompts and outputs never enter this table."""
    if record_id is not None:
        record = await db.scalar(
            select(OpenAPIUsageRecord)
            .where(
                OpenAPIUsageRecord.id == record_id,
                OpenAPIUsageRecord.profile_id == profile_id,
            )
            .with_for_update()
        )
        if record is None:
            raise ValueError("Open API usage reservation not found")
    else:
        record = OpenAPIUsageRecord(profile_id=profile_id)
        db.add(record)

    record.request_id = request_id
    record.provider = provider[:64]
    record.model = model[:128]
    record.prompt_tokens = max(0, int(prompt_tokens))
    record.completion_tokens = max(0, int(completion_tokens))
    record.total_tokens = max(0, int(total_tokens))
    record.status = "success" if success else "failed"
    record.error_category = error_category[:50] if error_category else None
    await db.commit()
    return record


async def reserve_usage(
    db: AsyncSession,
    *,
    profile_id: int,
    request_id: str | None,
    provider: str,
    model: str,
    requested_tokens: int,
) -> tuple[OpenAPIUsageRecord, int]:
    """Atomically reserve one Open API request and its requested token budget.

    PostgreSQL serializes reservations for a profile by locking the profile row;
    SQLite keeps the same transaction shape for local/test deployments.  A
    crashed worker leaves a bounded reservation that is released after ten
    minutes, while the request itself remains counted for abuse protection.
    """
    await db.execute(
        select(UserProfile.id)
        .where(UserProfile.id == profile_id)
        .with_for_update()
    )
    await db.execute(
        update(OpenAPIUsageRecord)
        .where(
            OpenAPIUsageRecord.profile_id == profile_id,
            OpenAPIUsageRecord.status == "reserved",
            OpenAPIUsageRecord.created_at < datetime.now(timezone.utc).replace(tzinfo=None) - _RESERVATION_TTL,
        )
        .values(status="expired", total_tokens=0, error_category="reservation_expired")
    )

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
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Open API daily request quota exceeded",
            headers={"Retry-After": "3600"},
        )
    if used_tokens + requested_tokens > settings.open_api_daily_token_quota:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Open API daily token quota exceeded",
            headers={"Retry-After": "3600"},
        )

    record = OpenAPIUsageRecord(
        profile_id=profile_id,
        request_id=request_id,
        provider=provider[:64],
        model=model[:128],
        total_tokens=max(0, int(requested_tokens)),
        status="reserved",
    )
    db.add(record)
    await db.flush()
    await db.commit()
    return record, used_tokens
