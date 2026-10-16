"""V1 collaboration permission and invitation tests."""

import pytest
from sqlalchemy import select

from app.api.deps_auth import get_current_profile
from app.main import app
from app.models.collaboration import ProjectMember
from app.models.survey import SurveyProject, UserProfile
from app.models.user import UserAccount


async def _create_project(client):
    response = await client.post("/api/v1/projects", json={"title": "shared study"})
    assert response.status_code == 200
    return response.json()["id"]


async def _create_second_profile(db_session):
    user = UserAccount(
        email="second-researcher@example.invalid",
        hashed_password="test-only-not-a-password-hash",
        display_name="Second Researcher",
        role="researcher",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    profile = UserProfile(user_id=user.id, role="researcher")
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_owner_can_invite_accept_and_manage_role(client, db_session):
    project_id = await _create_project(client)
    second_profile = await _create_second_profile(db_session)

    invitation = await client.post(
        f"/api/v1/collaboration/projects/{project_id}/invitations",
        json={"invitee_profile_id": second_profile.id, "role": "reviewer"},
    )
    assert invitation.status_code == 200
    invitation_id = invitation.json()["invitation"]["id"]

    duplicate = await client.post(
        f"/api/v1/collaboration/projects/{project_id}/invitations",
        json={"invitee_profile_id": second_profile.id, "role": "reviewer"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["idempotent"] is True

    app.dependency_overrides[get_current_profile] = lambda: second_profile
    try:
        pending = await client.get("/api/v1/collaboration/invitations")
        assert pending.status_code == 200
        assert pending.json()["invitations"][0]["id"] == invitation_id

        accepted = await client.post(f"/api/v1/collaboration/invitations/{invitation_id}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["member"]["role"] == "reviewer"

        forbidden = await client.post(
            f"/api/v1/collaboration/projects/{project_id}/invitations",
            json={"invitee_profile_id": second_profile.id, "role": "viewer"},
        )
        assert forbidden.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_profile, None)

    members = await client.get(f"/api/v1/collaboration/projects/{project_id}/members")
    assert members.status_code == 200
    member = next(item for item in members.json()["members"] if item["profile_id"] == second_profile.id)

    member_page = await client.get(
        f"/api/v1/collaboration/projects/{project_id}/members?limit=1"
    )
    assert member_page.status_code == 200
    assert member_page.json()["pagination"] == {
        "limit": 1,
        "offset": 0,
        "has_more": True,
        "next_offset": 1,
    }

    updated = await client.patch(
        f"/api/v1/collaboration/projects/{project_id}/members/{member['id']}",
        json={"role": "editor"},
    )
    assert updated.status_code == 200
    assert updated.json()["member"]["role"] == "editor"

    audit = await client.get(f"/api/v1/collaboration/projects/{project_id}/audit")
    assert audit.status_code == 200
    event_types = {event["event_type"] for event in audit.json()["events"]}
    assert {"invitation.created", "invitation.accepted", "member.role_updated"} <= event_types

    audit_page = await client.get(
        f"/api/v1/collaboration/projects/{project_id}/audit?limit=1"
    )
    assert audit_page.status_code == 200
    assert audit_page.json()["pagination"]["has_more"] is True


@pytest.mark.asyncio
async def test_non_member_cannot_read_or_mutate_foreign_project(client, db_session):
    project_id = await _create_project(client)
    second_profile = await _create_second_profile(db_session)
    app.dependency_overrides[get_current_profile] = lambda: second_profile
    try:
        members = await client.get(f"/api/v1/collaboration/projects/{project_id}/members")
        assert members.status_code == 404
        invite = await client.post(
            f"/api/v1/collaboration/projects/{project_id}/invitations",
            json={"invitee_profile_id": second_profile.id, "role": "viewer"},
        )
        assert invite.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_profile, None)


@pytest.mark.asyncio
async def test_owner_row_is_created_for_new_project(client, db_session):
    project_id = await _create_project(client)
    result = await db_session.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    members = result.scalars().all()
    assert len(members) == 1
    assert members[0].role == "owner"
