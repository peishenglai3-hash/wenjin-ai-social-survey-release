"""Copilot project-context ownership regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from starlette.responses import StreamingResponse

from app.api.v1.router_copilot import copilot_chat, copilot_chat_stream
from app.models.survey import SurveyProject, UserProfile
from app.models.user import UserAccount


async def _current_profile(db_session):
    return await db_session.scalar(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )


async def _foreign_project(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    project = SurveyProject(
        profile_id=profile.id,
        title="private foreign project",
        research_direction="private foreign direction",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


class TestCopilotProjectOwnership:
    @pytest.mark.asyncio
    async def test_non_streaming_copilot_rejects_foreign_project(self, client, db_session):
        project = await _foreign_project(db_session)
        ai = AsyncMock()

        result = await copilot_chat(
            payload={"project_id": project.id, "message": "summarize this"},
            profile=await _current_profile(db_session),
            ai=ai,
            db=db_session,
        )

        assert result == {"error": "Project not found"}
        ai.chat.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_streaming_copilot_rejects_foreign_project(self, client, db_session):
        project = await _foreign_project(db_session)
        ai = AsyncMock()

        response = await copilot_chat_stream(
            payload={"project_id": project.id, "message": "summarize this"},
            profile=await _current_profile(db_session),
            ai=ai,
            db=db_session,
        )

        assert isinstance(response, StreamingResponse)
        chunks = [chunk async for chunk in response.body_iterator]
        assert "Project not found" in "".join(chunks)
        ai.chat_stream.assert_not_awaited()
