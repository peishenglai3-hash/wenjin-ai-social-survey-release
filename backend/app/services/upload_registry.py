"""Ownership and bounded-retention helpers for uploaded media."""

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.upload import UploadedFile


def _now_utc_naive() -> datetime:
    return datetime.utcnow()


def resolve_upload_path(row: UploadedFile) -> Path | None:
    """Resolve a server-created storage name without allowing path traversal."""
    root = Path(settings.upload_dir).resolve()
    candidate = (root / row.storage_name).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


async def cleanup_expired_uploads(db: AsyncSession) -> int:
    """Delete expired records and their files; returns the number of records."""
    result = await db.execute(
        select(UploadedFile).where(UploadedFile.expires_at <= _now_utc_naive())
    )
    rows = result.scalars().all()
    for row in rows:
        path = resolve_upload_path(row)
        if path is not None:
            path.unlink(missing_ok=True)
        await db.delete(row)
    if rows:
        await db.flush()
    return len(rows)


async def register_upload(
    db: AsyncSession,
    *,
    profile_id: int,
    file_id: str,
    storage_name: str,
    suffix: str,
    size_bytes: int,
) -> UploadedFile:
    row = UploadedFile(
        file_id=file_id,
        profile_id=profile_id,
        storage_name=storage_name,
        suffix=suffix,
        size_bytes=size_bytes,
        status="active",
        expires_at=_now_utc_naive() + timedelta(hours=settings.upload_retention_hours),
    )
    db.add(row)
    await db.flush()
    return row


async def get_owned_upload(
    db: AsyncSession,
    *,
    file_id: str,
    profile_id: int,
) -> tuple[UploadedFile, Path] | None:
    row = await db.scalar(
        select(UploadedFile).where(
            UploadedFile.file_id == file_id,
            UploadedFile.profile_id == profile_id,
            UploadedFile.status == "active",
        )
    )
    if row is None:
        return None
    if row.expires_at <= _now_utc_naive():
        path = resolve_upload_path(row)
        if path is not None:
            path.unlink(missing_ok=True)
        await db.delete(row)
        await db.commit()
        return None
    path = resolve_upload_path(row)
    if path is None:
        await db.delete(row)
        await db.commit()
        return None
    return row, path


async def consume_upload(db: AsyncSession, row: UploadedFile) -> None:
    """Remove a successfully consumed upload and its metadata."""
    path = resolve_upload_path(row)
    if path is not None:
        path.unlink(missing_ok=True)
    await db.delete(row)
    await db.commit()

