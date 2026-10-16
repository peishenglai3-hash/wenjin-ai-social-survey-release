"""Collaborative research artifact API without realtime editing or raw-source sharing."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import get_current_profile
from app.api.pagination import take_page
from app.models.research_artifact import (
    ResearchArtifact,
    ResearchArtifactVersion,
    ResearchReviewTask,
)
from app.models.survey import UserProfile
from app.schemas.research_artifact import (
    AnnotationCreate,
    ArtifactCreate,
    ReviewDecision,
    ReviewTaskCreate,
    ShareCreate,
    ShareResolve,
    VersionCreate,
)
from app.services.research_artifact import (
    ResearchArtifactService,
    _annotation_payload,
    _artifact_payload,
    _review_payload,
    _version_payload,
)
from app.services.collaboration import get_project_for_access

router = APIRouter(prefix="/collaboration", tags=["collaboration-artifacts"])


@router.post("/projects/{project_id}/artifacts", status_code=status.HTTP_201_CREATED)
async def create_artifact(
    project_id: int,
    payload: ArtifactCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    artifact, created = await ResearchArtifactService.create_artifact(
        db,
        project_id,
        profile,
        artifact_key=payload.artifact_key,
        kind=payload.kind,
        title=payload.title,
    )
    return {"created": created, "artifact": _artifact_payload(artifact)}


@router.get("/projects/{project_id}/artifacts")
async def list_artifacts(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    await get_project_for_access(db, project_id, profile.id)
    result = await db.execute(
        select(ResearchArtifact)
        .where(ResearchArtifact.project_id == project_id, ResearchArtifact.status == "active")
        .order_by(ResearchArtifact.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    artifacts, pagination = take_page(result.scalars().all(), limit=limit, offset=offset)
    return {"artifacts": [_artifact_payload(item) for item in artifacts], "pagination": pagination}


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    artifact = await ResearchArtifactService.get_artifact(db, artifact_id, profile)
    return {"artifact": _artifact_payload(artifact)}


@router.post("/artifacts/{artifact_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(
    artifact_id: int,
    payload: VersionCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    artifact = await ResearchArtifactService.get_artifact(db, artifact_id, profile)
    version, created = await ResearchArtifactService.create_version(db, artifact, profile, payload)
    return {"created": created, "version": _version_payload(version)}


@router.get("/artifacts/{artifact_id}/versions")
async def list_versions(
    artifact_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    artifact = await ResearchArtifactService.get_artifact(db, artifact_id, profile)
    versions, has_more = await ResearchArtifactService.list_versions(
        db, artifact, limit=limit, offset=offset
    )
    return {
        "versions": [_version_payload(item) for item in versions],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }


@router.get("/versions/{version_id}")
async def get_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    return {"version": _version_payload(version)}


@router.post("/versions/{version_id}/annotations", status_code=status.HTTP_201_CREATED)
async def create_annotation(
    version_id: int,
    payload: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    annotation = await ResearchArtifactService.add_annotation(db, version, profile, payload)
    return {"annotation": _annotation_payload(annotation)}


@router.get("/versions/{version_id}/annotations")
async def list_annotations(
    version_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    annotations, has_more = await ResearchArtifactService.list_annotations(
        db, version, limit=limit, offset=offset
    )
    return {
        "annotations": [_annotation_payload(item) for item in annotations],
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + limit if has_more else None,
        },
    }


@router.post("/versions/{version_id}/review-tasks", status_code=status.HTTP_201_CREATED)
async def create_review_task(
    version_id: int,
    payload: ReviewTaskCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    task = await ResearchArtifactService.create_review_task(db, version, profile, payload)
    return {"review_task": _review_payload(task)}


@router.get("/versions/{version_id}/review-tasks")
async def list_review_tasks(
    version_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    result = await db.execute(
        select(ResearchReviewTask)
        .where(ResearchReviewTask.version_id == version.id)
        .order_by(ResearchReviewTask.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    tasks, pagination = take_page(result.scalars().all(), limit=limit, offset=offset)
    return {"review_tasks": [_review_payload(item) for item in tasks], "pagination": pagination}


@router.post("/review-tasks/{task_id}/decision")
async def decide_review_task(
    task_id: int,
    payload: ReviewDecision,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    task = await ResearchArtifactService.decide_review(db, task_id, profile, payload)
    return {"review_task": _review_payload(task)}


@router.post("/versions/{version_id}/shares", status_code=status.HTTP_201_CREATED)
async def create_share(
    version_id: int,
    payload: ShareCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    version = await ResearchArtifactService.get_version(db, version_id, profile)
    share, token = await ResearchArtifactService.create_share(db, version, profile, payload)
    return {
        "share": {
            "id": share.id,
            "version_id": share.version_id,
            "audience": share.audience,
            "expires_at": share.expires_at.isoformat(),
            "status": share.status,
        },
        "share_token": token,
        "warning": "The token is returned once and is not stored in plaintext.",
    }


@router.post("/shares/resolve")
async def resolve_share(
    payload: ShareResolve,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    _, version, artifact = await ResearchArtifactService.resolve_share(db, payload.share_token)
    return {
        "artifact": _artifact_payload(artifact),
        "version": _version_payload(version),
        "share_scope": "redacted_version_only",
    }


@router.post("/shares/{share_id}/revoke")
async def revoke_share(
    share_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    share = await ResearchArtifactService.revoke_share(db, share_id, profile)
    return {
        "share": {
            "id": share.id,
            "version_id": share.version_id,
            "status": share.status,
            "revoked_at": share.revoked_at.isoformat() if share.revoked_at else None,
        }
    }
