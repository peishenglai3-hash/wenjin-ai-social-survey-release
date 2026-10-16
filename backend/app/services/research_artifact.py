"""Safe collaboration artifact lifecycle with redaction and review gates."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_artifact import (
    ResearchAnnotation,
    ResearchArtifact,
    ResearchArtifactVersion,
    ResearchReviewTask,
    ResearchShare,
)
from app.models.survey import UserProfile
from app.services.collaboration import ROLE_RANK, add_audit_event, get_project_for_access

_SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _assert_safe_text(value: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Content contains a credential or direct identifier; redact it before submission",
        )


def _artifact_payload(artifact: ResearchArtifact) -> dict:
    return {
        "id": artifact.id,
        "project_id": artifact.project_id,
        "artifact_key": artifact.artifact_key,
        "kind": artifact.kind,
        "title": artifact.title,
        "created_by_profile_id": artifact.created_by_profile_id,
        "status": artifact.status,
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "updated_at": artifact.updated_at.isoformat() if artifact.updated_at else None,
    }


def _version_payload(version: ResearchArtifactVersion) -> dict:
    return {
        "id": version.id,
        "artifact_id": version.artifact_id,
        "version_number": version.version_number,
        "created_by_profile_id": version.created_by_profile_id,
        "status": version.status,
        "redaction_status": version.redaction_status,
        "redacted_content": version.redacted_content,
        "content_sha256": version.content_sha256,
        "redaction_note": version.redaction_note,
        "change_summary": version.change_summary,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def _annotation_payload(annotation: ResearchAnnotation) -> dict:
    return {
        "id": annotation.id,
        "version_id": annotation.version_id,
        "author_profile_id": annotation.author_profile_id,
        "body": annotation.body,
        "anchor_start": annotation.anchor_start,
        "anchor_end": annotation.anchor_end,
        "status": annotation.status,
        "resolution_note": annotation.resolution_note,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
    }


def _review_payload(task: ResearchReviewTask) -> dict:
    return {
        "id": task.id,
        "version_id": task.version_id,
        "requested_by_profile_id": task.requested_by_profile_id,
        "reviewer_profile_id": task.reviewer_profile_id,
        "status": task.status,
        "request_note": task.request_note,
        "decision_note": task.decision_note,
        "decided_at": task.decided_at.isoformat() if task.decided_at else None,
    }


class ResearchArtifactService:
    @staticmethod
    async def create_artifact(
        db: AsyncSession, project_id: int, profile: UserProfile, *, artifact_key: str,
        kind: str, title: str,
    ) -> tuple[ResearchArtifact, bool]:
        project, role = await get_project_for_access(
            db, project_id, profile.id, minimum_role="editor"
        )
        if ROLE_RANK.get(role, 0) < ROLE_RANK["editor"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
        existing = await db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.project_id == project.id,
                ResearchArtifact.artifact_key == artifact_key,
            )
        )
        if existing:
            return existing, False
        artifact = ResearchArtifact(
            project_id=project.id,
            artifact_key=artifact_key,
            kind=kind,
            title=title,
            created_by_profile_id=profile.id,
        )
        db.add(artifact)
        await db.flush()
        add_audit_event(
            db,
            project_id=project.id,
            actor_profile_id=profile.id,
            event_type="artifact.created",
            target_type="artifact",
            target_id=artifact.id,
            details={"artifact_key": artifact_key, "kind": kind},
        )
        await db.commit()
        await db.refresh(artifact)
        return artifact, True

    @staticmethod
    async def get_artifact(db: AsyncSession, artifact_id: int, profile: UserProfile) -> ResearchArtifact:
        artifact = await db.scalar(select(ResearchArtifact).where(ResearchArtifact.id == artifact_id))
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        await get_project_for_access(db, artifact.project_id, profile.id)
        return artifact

    @staticmethod
    async def create_version(
        db: AsyncSession, artifact: ResearchArtifact, profile: UserProfile, payload
    ) -> tuple[ResearchArtifactVersion, bool]:
        _, role = await get_project_for_access(
            db, artifact.project_id, profile.id, minimum_role="editor"
        )
        if ROLE_RANK.get(role, 0) < ROLE_RANK["editor"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
        _assert_safe_text(payload.redacted_content)
        _assert_safe_text(payload.redaction_note)
        if payload.idempotency_key:
            existing = await db.scalar(
                select(ResearchArtifactVersion).where(
                    ResearchArtifactVersion.artifact_id == artifact.id,
                    ResearchArtifactVersion.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return existing, False
        if payload.version_number is None:
            latest = await db.scalar(
                select(func.max(ResearchArtifactVersion.version_number)).where(
                    ResearchArtifactVersion.artifact_id == artifact.id
                )
            )
            version_number = (latest or 0) + 1
        else:
            version_number = payload.version_number
        version = ResearchArtifactVersion(
            artifact_id=artifact.id,
            version_number=version_number,
            created_by_profile_id=profile.id,
            redaction_status="redacted",
            redacted_content=payload.redacted_content,
            content_sha256=hashlib.sha256(payload.redacted_content.encode("utf-8")).hexdigest(),
            redaction_note=payload.redaction_note,
            change_summary=payload.change_summary,
            idempotency_key=payload.idempotency_key,
            status="draft",
        )
        db.add(version)
        await db.flush()
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.version.created",
            target_type="artifact_version",
            target_id=version.id,
            details={"artifact_id": artifact.id, "version_number": version_number},
        )
        await db.commit()
        await db.refresh(version)
        return version, True

    @staticmethod
    async def list_versions(db: AsyncSession, artifact: ResearchArtifact) -> list[ResearchArtifactVersion]:
        result = await db.execute(
            select(ResearchArtifactVersion)
            .where(ResearchArtifactVersion.artifact_id == artifact.id)
            .order_by(ResearchArtifactVersion.version_number.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_version(db: AsyncSession, version_id: int, profile: UserProfile) -> ResearchArtifactVersion:
        version = await db.scalar(
            select(ResearchArtifactVersion).where(ResearchArtifactVersion.id == version_id)
        )
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
        artifact = await db.scalar(select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id))
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        await get_project_for_access(db, artifact.project_id, profile.id)
        return version

    @staticmethod
    async def add_annotation(
        db: AsyncSession, version: ResearchArtifactVersion, profile: UserProfile, payload
    ) -> ResearchAnnotation:
        artifact = await db.scalar(select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id))
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        await get_project_for_access(db, artifact.project_id, profile.id)
        _assert_safe_text(payload.body)
        annotation = ResearchAnnotation(
            version_id=version.id,
            author_profile_id=profile.id,
            body=payload.body,
            anchor_start=payload.anchor_start,
            anchor_end=payload.anchor_end,
        )
        db.add(annotation)
        await db.flush()
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.annotation.created",
            target_type="annotation",
            target_id=annotation.id,
            details={"version_id": version.id},
        )
        await db.commit()
        await db.refresh(annotation)
        return annotation

    @staticmethod
    async def list_annotations(db: AsyncSession, version: ResearchArtifactVersion) -> list[ResearchAnnotation]:
        result = await db.execute(
            select(ResearchAnnotation)
            .where(ResearchAnnotation.version_id == version.id)
            .order_by(ResearchAnnotation.created_at)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_review_task(
        db: AsyncSession, version: ResearchArtifactVersion, profile: UserProfile, payload
    ) -> ResearchReviewTask:
        artifact = await db.scalar(select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id))
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        _, role = await get_project_for_access(
            db, artifact.project_id, profile.id, minimum_role="editor"
        )
        if ROLE_RANK.get(role, 0) < ROLE_RANK["editor"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
        if payload.reviewer_profile_id is not None:
            _, reviewer_role = await get_project_for_access(
                db, artifact.project_id, payload.reviewer_profile_id, minimum_role="reviewer"
            )
            if ROLE_RANK.get(reviewer_role, 0) < ROLE_RANK["reviewer"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reviewer is not eligible")
        task = ResearchReviewTask(
            version_id=version.id,
            requested_by_profile_id=profile.id,
            reviewer_profile_id=payload.reviewer_profile_id,
            request_note=payload.request_note,
            status="pending",
        )
        db.add(task)
        version.status = "submitted"
        await db.flush()
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.review.requested",
            target_type="review_task",
            target_id=task.id,
            details={"version_id": version.id, "reviewer_profile_id": payload.reviewer_profile_id},
        )
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def decide_review(
        db: AsyncSession, task_id: int, profile: UserProfile, payload
    ) -> ResearchReviewTask:
        task = await db.scalar(select(ResearchReviewTask).where(ResearchReviewTask.id == task_id))
        if task is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")
        version = await db.scalar(
            select(ResearchArtifactVersion).where(ResearchArtifactVersion.id == task.version_id)
        )
        artifact = await db.scalar(
            select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id)
        ) if version else None
        if version is None or artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
        _, role = await get_project_for_access(
            db, artifact.project_id, profile.id, minimum_role="reviewer"
        )
        if task.reviewer_profile_id is not None and task.reviewer_profile_id != profile.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Assigned reviewer required")
        if ROLE_RANK.get(role, 0) < ROLE_RANK["reviewer"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer access required")
        if task.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review task is not pending")
        task.status = payload.status
        task.decision_note = payload.decision_note
        task.decided_at = _now()
        version.status = "approved" if payload.status == "approved" else (
            "draft" if payload.status == "changes_requested" else "rejected"
        )
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.review.decided",
            target_type="review_task",
            target_id=task.id,
            details={"version_id": version.id, "status": payload.status},
        )
        await db.commit()
        await db.refresh(task)
        return task

    @staticmethod
    async def create_share(
        db: AsyncSession, version: ResearchArtifactVersion, profile: UserProfile, payload
    ) -> tuple[ResearchShare, str]:
        artifact = await db.scalar(select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id))
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
        _, role = await get_project_for_access(
            db, artifact.project_id, profile.id, minimum_role="editor"
        )
        if ROLE_RANK.get(role, 0) < ROLE_RANK["editor"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
        if version.status != "approved" or version.redaction_status != "redacted":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved redacted versions can be shared")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        share = ResearchShare(
            version_id=version.id,
            created_by_profile_id=profile.id,
            token_digest=digest,
            audience=payload.audience,
            expires_at=_now() + timedelta(minutes=payload.expires_minutes),
            status="active",
        )
        db.add(share)
        await db.flush()
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.share.created",
            target_type="share",
            target_id=share.id,
            details={"version_id": version.id, "expires_minutes": payload.expires_minutes},
        )
        await db.commit()
        await db.refresh(share)
        return share, token

    @staticmethod
    async def resolve_share(db: AsyncSession, token: str) -> tuple[ResearchShare, ResearchArtifactVersion, ResearchArtifact]:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        share = await db.scalar(
            select(ResearchShare).where(
                ResearchShare.token_digest == digest,
                ResearchShare.status == "active",
                ResearchShare.expires_at > _now(),
            )
        )
        if share is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found or expired")
        version = await db.scalar(
            select(ResearchArtifactVersion).where(ResearchArtifactVersion.id == share.version_id)
        )
        artifact = await db.scalar(
            select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id)
        ) if version else None
        if version is None or artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
        return share, version, artifact

    @staticmethod
    async def revoke_share(db: AsyncSession, share_id: int, profile: UserProfile) -> ResearchShare:
        share = await db.scalar(select(ResearchShare).where(ResearchShare.id == share_id))
        if share is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
        version = await db.scalar(
            select(ResearchArtifactVersion).where(ResearchArtifactVersion.id == share.version_id)
        )
        artifact = await db.scalar(
            select(ResearchArtifact).where(ResearchArtifact.id == version.artifact_id)
        ) if version else None
        if version is None or artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")
        _, role = await get_project_for_access(db, artifact.project_id, profile.id, minimum_role="editor")
        if ROLE_RANK.get(role, 0) < ROLE_RANK["editor"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editor access required")
        share.status = "revoked"
        share.revoked_at = _now()
        add_audit_event(
            db,
            project_id=artifact.project_id,
            actor_profile_id=profile.id,
            event_type="artifact.share.revoked",
            target_type="share",
            target_id=share.id,
            details={"version_id": version.id},
        )
        await db.commit()
        await db.refresh(share)
        return share
