"""Reflection session and source-context ownership tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_reflection import (
    _active_sessions,
    respond_to_reflection,
    start_reflection,
)
from app.models.survey import SurveyProject, SurveySession, UserProfile
from app.models.user import UserAccount


async def _current_user_and_profile(db_session):
    user = await db_session.scalar(
        select(UserAccount).where(UserAccount.email == "test-researcher@example.invalid")
    )
    profile = await db_session.scalar(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    return user, profile


async def _foreign_project_and_session(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    project = SurveyProject(profile_id=profile.id, title="foreign reflection project")
    db_session.add(project)
    await db_session.flush()
    session = SurveySession(project_id=project.id, transcript_text="private reflection transcript")
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(session)
    return profile, project, session


@pytest.mark.asyncio
async def test_start_reflection_rejects_foreign_project_and_source(db_session, client):
    user, profile = await _current_user_and_profile(db_session)
    _, foreign_project, foreign_session = await _foreign_project_and_session(db_session)
    ai = AsyncMock()

    result = await start_reflection(
        {"trigger_type": "fieldwork_completed", "project_id": foreign_project.id},
        user=user,
        profile=profile,
        ai=ai,
        db=db_session,
    )
    assert result == {"error": "Project not found"}
    ai.chat.assert_not_awaited()

    result = await start_reflection(
        {"trigger_type": "fieldwork_completed", "source_session_id": foreign_session.id},
        user=user,
        profile=profile,
        ai=ai,
        db=db_session,
    )
    assert result == {"error": "Survey session not found"}
    ai.chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_reflection_session_cannot_be_answered_by_another_profile(db_session, client):
    _, current_profile = await _current_user_and_profile(db_session)
    foreign_profile, _, _ = await _foreign_project_and_session(db_session)
    session_id = "foreign-reflection-session"
    _active_sessions[session_id] = {
        "profile_id": foreign_profile.id,
        "questions": [{"question": "private?"}],
        "answers": [],
    }
    ai = AsyncMock()

    try:
        result = await respond_to_reflection(
            {"session_id": session_id, "answer": "attempt"},
            profile=current_profile,
            ai=ai,
        )
    finally:
        _active_sessions.pop(session_id, None)

    assert result == {"error": "Session not found or expired. Please start a new reflection."}
    assert not ai.mock_calls
