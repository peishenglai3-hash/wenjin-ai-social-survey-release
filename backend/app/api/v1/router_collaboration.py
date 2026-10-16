"""Project membership, invitations, roles, and metadata-only audit events."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_auth import get_current_profile
from app.models.collaboration import ProjectAuditEvent, ProjectInvitation, ProjectMember
from app.models.survey import SurveyProject, UserProfile
from app.schemas.collaboration import InvitationCreate, MemberRoleUpdate
from app.services.collaboration import (
    add_audit_event,
    ensure_owner_membership,
    get_project_for_access,
)

router = APIRouter(prefix="/collaboration", tags=["collaboration"])


def _member_payload(member: ProjectMember) -> dict:
    return {
        "id": member.id,
        "project_id": member.project_id,
        "profile_id": member.profile_id,
        "role": member.role,
        "status": member.status,
        "created_at": str(member.created_at) if member.created_at else None,
        "updated_at": str(member.updated_at) if member.updated_at else None,
    }


def _invitation_payload(invitation: ProjectInvitation) -> dict:
    return {
        "id": invitation.id,
        "project_id": invitation.project_id,
        "invitee_profile_id": invitation.invitee_profile_id,
        "role": invitation.role,
        "status": invitation.status,
        "created_at": str(invitation.created_at) if invitation.created_at else None,
    }


@router.get("/projects/{project_id}/members")
async def list_members(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    project, _ = await get_project_for_access(db, project_id, profile.id)
    await ensure_owner_membership(db, project)
    await db.commit()
    result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id, ProjectMember.status == "active")
        .order_by(ProjectMember.id)
    )
    return {"project_id": project_id, "members": [_member_payload(item) for item in result.scalars().all()]}


@router.post("/projects/{project_id}/invitations")
async def create_invitation(
    project_id: int,
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    project, role = await get_project_for_access(db, project_id, profile.id, minimum_role="owner")
    if role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    if payload.invitee_profile_id == profile.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot invite yourself")

    invitee = await db.scalar(select(UserProfile).where(UserProfile.id == payload.invitee_profile_id))
    if invitee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitee not found")

    existing_member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.profile_id == payload.invitee_profile_id,
            ProjectMember.status == "active",
        )
    )
    if existing_member is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Profile is already a project member")

    existing = await db.scalar(
        select(ProjectInvitation).where(
            ProjectInvitation.project_id == project_id,
            ProjectInvitation.invitee_profile_id == payload.invitee_profile_id,
            ProjectInvitation.status == "pending",
        )
    )
    if existing is not None:
        return {"invitation": _invitation_payload(existing), "idempotent": True}

    invitation = ProjectInvitation(
        project_id=project.id,
        invitee_profile_id=payload.invitee_profile_id,
        inviter_profile_id=profile.id,
        role=payload.role,
        status="pending",
    )
    db.add(invitation)
    await db.flush()
    add_audit_event(
        db,
        project_id=project.id,
        actor_profile_id=profile.id,
        event_type="invitation.created",
        target_type="invitation",
        target_id=invitation.id,
        details={"invitee_profile_id": payload.invitee_profile_id, "role": payload.role},
    )
    await db.commit()
    await db.refresh(invitation)
    return {"invitation": _invitation_payload(invitation), "idempotent": False}


@router.get("/invitations")
async def list_my_invitations(
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    result = await db.execute(
        select(ProjectInvitation)
        .where(
            ProjectInvitation.invitee_profile_id == profile.id,
            ProjectInvitation.status == "pending",
        )
        .order_by(ProjectInvitation.created_at.desc())
    )
    return {"invitations": [_invitation_payload(item) for item in result.scalars().all()]}


@router.post("/invitations/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    invitation = await db.scalar(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.invitee_profile_id == profile.id,
            ProjectInvitation.status == "pending",
        )
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    project = await db.scalar(select(SurveyProject).where(SurveyProject.id == invitation.project_id))
    if project is None:
        invitation.status = "revoked"
        invitation.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == invitation.project_id,
            ProjectMember.profile_id == profile.id,
        )
    )
    if member is None:
        member = ProjectMember(
            project_id=invitation.project_id,
            profile_id=profile.id,
            role=invitation.role,
            status="active",
            invited_by_profile_id=invitation.inviter_profile_id,
        )
        db.add(member)
    else:
        member.role = invitation.role
        member.status = "active"
    invitation.status = "accepted"
    invitation.accepted_at = datetime.now(timezone.utc)
    await db.flush()
    add_audit_event(
        db,
        project_id=project.id,
        actor_profile_id=profile.id,
        event_type="invitation.accepted",
        target_type="member",
        target_id=member.id,
        details={"role": member.role},
    )
    await db.commit()
    await db.refresh(member)
    return {"member": _member_payload(member)}


@router.post("/invitations/{invitation_id}/reject")
async def reject_invitation(
    invitation_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    invitation = await db.scalar(
        select(ProjectInvitation).where(
            ProjectInvitation.id == invitation_id,
            ProjectInvitation.invitee_profile_id == profile.id,
            ProjectInvitation.status == "pending",
        )
    )
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    invitation.status = "rejected"
    await db.commit()
    return {"id": invitation.id, "status": invitation.status}


@router.patch("/projects/{project_id}/members/{member_id}")
async def update_member_role(
    project_id: int,
    member_id: int,
    payload: MemberRoleUpdate,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    _, role = await get_project_for_access(db, project_id, profile.id, minimum_role="owner")
    if role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.status == "active",
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner role cannot be changed")
    member.role = payload.role
    add_audit_event(
        db,
        project_id=project_id,
        actor_profile_id=profile.id,
        event_type="member.role_updated",
        target_type="member",
        target_id=member.id,
        details={"role": payload.role},
    )
    await db.commit()
    await db.refresh(member)
    return {"member": _member_payload(member)}


@router.delete("/projects/{project_id}/members/{member_id}")
async def remove_member(
    project_id: int,
    member_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    _, role = await get_project_for_access(db, project_id, profile.id, minimum_role="owner")
    if role != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required")
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.status == "active",
        )
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member.role == "owner":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner cannot be removed")
    target_id = member.id
    await db.delete(member)
    add_audit_event(
        db,
        project_id=project_id,
        actor_profile_id=profile.id,
        event_type="member.removed",
        target_type="member",
        target_id=target_id,
    )
    await db.commit()
    return {"id": target_id, "removed": True}


@router.get("/projects/{project_id}/audit")
async def list_audit_events(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    profile: UserProfile = Depends(get_current_profile),
):
    await get_project_for_access(db, project_id, profile.id)
    result = await db.execute(
        select(ProjectAuditEvent)
        .where(ProjectAuditEvent.project_id == project_id)
        .order_by(ProjectAuditEvent.created_at.desc())
        .limit(100)
    )
    return {
        "events": [
            {
                "id": event.id,
                "actor_profile_id": event.actor_profile_id,
                "event_type": event.event_type,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "details": event.details_json,
                "request_id": event.request_id,
                "created_at": str(event.created_at) if event.created_at else None,
            }
            for event in result.scalars().all()
        ]
    }

