"""Fieldwork session ownership regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_fieldwork import regenerate_notes
from app.models.survey import SurveyProject, SurveySession, UserProfile
from app.models.user import UserAccount


async def _current_profile(db_session):
    result = await db_session.execute(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )
    return result.scalar_one()


async def _foreign_session(db_session):
    foreign_profile = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign_profile)
    await db_session.flush()
    project = SurveyProject(profile_id=foreign_profile.id, title="foreign fieldwork project")
    db_session.add(project)
    await db_session.flush()
    session = SurveySession(
        project_id=project.id,
        transcript_text="private foreign transcript",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return project, session


class TestFieldworkSessionOwnership:
    @pytest.mark.asyncio
    async def test_create_allows_current_profile_project(self, client, db_session):
        profile = await _current_profile(db_session)
        project = SurveyProject(profile_id=profile.id, title="owned fieldwork project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        response = await client.post(
            "/api/v1/fieldwork/sessions",
            json={"project_id": project.id, "transcript_text": "short transcript"},
        )

        assert response.status_code == 200
        assert response.json()["project_id"] == project.id

    @pytest.mark.asyncio
    async def test_create_rejects_foreign_project(self, client, db_session):
        project, _ = await _foreign_session(db_session)

        response = await client.post(
            "/api/v1/fieldwork/sessions",
            json={"project_id": project.id, "transcript_text": "new transcript"},
        )

        assert response.json() == {"error": "Project not found"}

    @pytest.mark.asyncio
    async def test_update_and_read_routes_hide_foreign_session(self, client, db_session):
        _, session = await _foreign_session(db_session)

        update = await client.patch(
            f"/api/v1/fieldwork/sessions/{session.id}",
            json={"transcript_text": "tampered"},
        )
        notes = await client.get(f"/api/v1/fieldwork/sessions/{session.id}/notes")
        exported = await client.get(
            f"/api/v1/fieldwork/sessions/{session.id}/notes/export"
        )

        assert update.json() == {"error": "Session not found"}
        assert notes.json() == {"error": "Session not found"}
        assert exported.json() == {"error": "Session not found"}
        await db_session.refresh(session)
        assert session.transcript_text == "private foreign transcript"

    @pytest.mark.asyncio
    async def test_regeneration_does_not_send_foreign_session_to_ai(
        self,
        client,
        db_session,
    ):
        _, session = await _foreign_session(db_session)
        ai = AsyncMock()

        result = await regenerate_notes(
            session.id,
            payload={"transcript_text": "private foreign transcript"},
            db=db_session,
            ai=ai,
            profile=await _current_profile(db_session),
        )

        assert result == {"error": "Session not found"}
        ai.chat.assert_not_awaited()
