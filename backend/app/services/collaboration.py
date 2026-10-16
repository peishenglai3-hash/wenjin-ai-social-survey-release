"""Permission helpers for project collaboration V1."""

import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration import ProjectAuditEvent, ProjectMember
from app.models.survey import SurveyProject

ROLE_RANK = {"viewer": 10, "reviewer": 20, "editor": 30, "owner": 40}


async def get_project_for_access(
    db: AsyncSession,
    project_id: int,
    profile_id: int,
    *,
    minimum_role: str = "viewer",
) -> tuple[SurveyProject, str]:
    """Return a project and effective role, hiding inaccessible projects as 404."""
    project = await db.scalar(select(SurveyProject).where(SurveyProject.id == project_id))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.profile_id == profile_id:
        return project, "owner"

    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.profile_id == profile_id,
            ProjectMember.status == "active",
        )
    )
    if member is None or ROLE_RANK.get(member.role, 0) < ROLE_RANK.get(minimum_role, 0):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project, member.role


async def ensure_owner_membership(
    db: AsyncSession,
    project: SurveyProject,
) -> ProjectMember:
    """Backfill the owner row for projects created before collaboration V1."""
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.profile_id == project.profile_id,
        )
    )
    if member is None:
        member = ProjectMember(
            project_id=project.id,
            profile_id=project.profile_id,
            role="owner",
            status="active",
        )
        db.add(member)
        await db.flush()
    elif member.role != "owner" or member.status != "active":
        member.role = "owner"
        member.status = "active"
        await db.flush()
    return member


def add_audit_event(
    db: AsyncSession,
    *,
    project_id: int,
    actor_profile_id: int,
    event_type: str,
    target_type: str = "project",
    target_id: int | None = None,
    details: dict | None = None,
) -> ProjectAuditEvent:
    """Record metadata only; callers must not place raw research content here."""
    event = ProjectAuditEvent(
        project_id=project_id,
        actor_profile_id=actor_profile_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        details_json=json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
    )
    db.add(event)
    return event
