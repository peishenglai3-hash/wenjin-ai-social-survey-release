"""Coding/codebook ownership and request-field boundary tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_coding import (
    add_code,
    ai_suggest_codes,
    create_assignment,
    edit_code,
    get_assignments,
    get_codebook,
)
from app.models.survey import (
    CodebookCode,
    CodingAssignment,
    SurveyProject,
    SurveySession,
    UserProfile,
)
from app.models.user import UserAccount


async def _current_profile(db_session):
    return await db_session.scalar(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )


async def _foreign_code_and_session(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    project = SurveyProject(profile_id=profile.id, title="foreign coding project")
    db_session.add(project)
    await db_session.flush()
    session = SurveySession(project_id=project.id, transcript_text="private transcript")
    code = CodebookCode(project_id=project.id, name="private code")
    db_session.add_all([session, code])
    await db_session.commit()
    await db_session.refresh(session)
    await db_session.refresh(code)
    return project, session, code


@pytest.mark.asyncio
async def test_foreign_codebook_is_not_read_or_written(db_session, client):
    profile = await _current_profile(db_session)
    foreign_project, _, foreign_code = await _foreign_code_and_session(db_session)

    assert await get_codebook(
        foreign_project.id, profile=profile, db=db_session,
    ) == {"error": "Project not found"}
    assert await add_code(
        foreign_project.id,
        {"name": "should not exist", "created_by_profile_id": profile.id},
        profile=profile,
        db=db_session,
    ) == {"error": "Project not found"}
    assert await edit_code(
        foreign_code.id,
        {"name": "tampered", "project_id": profile.id},
        profile=profile,
        db=db_session,
    ) == {"error": "Code not found"}

    await db_session.refresh(foreign_code)
    assert foreign_code.name == "private code"


@pytest.mark.asyncio
async def test_cross_project_parent_is_rejected(db_session, client):
    profile = await _current_profile(db_session)
    foreign_project, _, foreign_code = await _foreign_code_and_session(db_session)
    own_project = SurveyProject(profile_id=profile.id, title="owned coding project")
    db_session.add(own_project)
    await db_session.commit()
    await db_session.refresh(own_project)

    result = await add_code(
        own_project.id,
        {"name": "child", "parent_code_id": foreign_code.id},
        profile=profile,
        db=db_session,
    )

    assert result == {"error": "Parent code not found"}
    assert await db_session.scalar(
        select(CodebookCode).where(
            CodebookCode.project_id == own_project.id,
            CodebookCode.name == "child",
        )
    ) is None
    assert foreign_project.id != own_project.id


@pytest.mark.asyncio
async def test_assignment_requires_owned_code_and_session(db_session, client):
    profile = await _current_profile(db_session)
    foreign_project, foreign_session, foreign_code = await _foreign_code_and_session(db_session)
    own_project = SurveyProject(profile_id=profile.id, title="owned coding project")
    db_session.add(own_project)
    await db_session.flush()
    own_session = SurveySession(project_id=own_project.id, transcript_text="owned transcript")
    own_code = CodebookCode(project_id=own_project.id, name="owned code")
    db_session.add_all([own_session, own_code])
    await db_session.commit()
    await db_session.refresh(own_session)
    await db_session.refresh(own_code)

    assert await create_assignment(
        {"code_id": foreign_code.id, "session_id": own_session.id},
        profile=profile,
        db=db_session,
    ) == {"error": "Code or session not found"}
    assert await create_assignment(
        {"code_id": own_code.id, "session_id": foreign_session.id},
        profile=profile,
        db=db_session,
    ) == {"error": "Code or session not found"}

    result = await create_assignment(
        {
            "code_id": own_code.id,
            "session_id": own_session.id,
            "coder_profile_id": 999999,
            "quote_text": "owned quote",
        },
        profile=profile,
        db=db_session,
    )
    assert result["id"]
    assignment = await db_session.get(CodingAssignment, result["id"])
    assert assignment.coder_profile_id == profile.id
    assert await get_assignments(foreign_session.id, profile=profile, db=db_session) == {
        "error": "Session not found"
    }


@pytest.mark.asyncio
async def test_suggestion_rejects_foreign_project_before_ai(db_session, client):
    profile = await _current_profile(db_session)
    foreign_project, _, _ = await _foreign_code_and_session(db_session)
    ai = AsyncMock()

    result = await ai_suggest_codes(
        {"project_id": foreign_project.id, "transcript": "private source"},
        profile=profile,
        db=db_session,
        ai=ai,
    )

    assert result == {"error": "Project not found"}
    ai.chat.assert_not_awaited()
