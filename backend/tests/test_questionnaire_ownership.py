"""Questionnaire and response ownership regression tests."""

import json

import pytest
from sqlalchemy import select

from app.models.survey import (
    Questionnaire,
    QuestionnaireResponse,
    SurveyProject,
    UserProfile,
)
from app.models.user import UserAccount


async def _foreign_questionnaire(db_session):
    foreign_profile = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign_profile)
    await db_session.flush()
    project = SurveyProject(profile_id=foreign_profile.id, title="foreign questionnaire project")
    db_session.add(project)
    await db_session.flush()
    questionnaire = Questionnaire(
        project_id=project.id,
        title="foreign questionnaire",
        questions_json=json.dumps([{"id": "q1", "text": "Question"}]),
    )
    db_session.add(questionnaire)
    await db_session.commit()
    await db_session.refresh(questionnaire)
    return project, questionnaire


class TestQuestionnaireOwnership:
    @pytest.mark.asyncio
    async def test_current_profile_can_save_and_read_questionnaire(
        self,
        client,
        db_session,
    ):
        profile = await db_session.scalar(
            select(UserProfile)
            .join(UserAccount, UserAccount.id == UserProfile.user_id)
            .where(UserAccount.email == "test-researcher@example.invalid")
        )
        project = SurveyProject(profile_id=profile.id, title="owned questionnaire project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)

        response = await client.post(
            "/api/v1/questionnaire/save",
            json={"project_id": project.id, "title": "owned questionnaire"},
        )

        assert response.status_code == 200
        assert response.json()["title"] == "owned questionnaire"

    @pytest.mark.asyncio
    async def test_save_rejects_foreign_project(self, client, db_session):
        project, _ = await _foreign_questionnaire(db_session)

        response = await client.post(
            "/api/v1/questionnaire/save",
            json={"project_id": project.id, "title": "tampered"},
        )

        assert response.status_code == 404
        assert await db_session.scalar(
            select(Questionnaire).where(Questionnaire.title == "tampered")
        ) is None

    @pytest.mark.asyncio
    async def test_foreign_questionnaire_is_hidden_from_reads(self, client, db_session):
        project, questionnaire = await _foreign_questionnaire(db_session)

        detail = await client.get(f"/api/v1/questionnaire/{questionnaire.id}")
        listing = await client.get(f"/api/v1/questionnaire/by-project/{project.id}")

        assert detail.status_code == 404
        assert listing.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_questionnaire_cannot_submit_read_stats_or_delete(
        self,
        client,
        db_session,
    ):
        _, questionnaire = await _foreign_questionnaire(db_session)

        submit = await client.post(
            f"/api/v1/questionnaire/{questionnaire.id}/respond",
            json={"answers": []},
        )
        responses = await client.get(
            f"/api/v1/questionnaire/{questionnaire.id}/responses"
        )
        stats = await client.get(f"/api/v1/questionnaire/{questionnaire.id}/stats")
        deleted = await client.delete(f"/api/v1/questionnaire/{questionnaire.id}")

        assert submit.status_code == 404
        assert responses.status_code == 404
        assert stats.status_code == 404
        assert deleted.status_code == 404
        persisted = await db_session.get(Questionnaire, questionnaire.id)
        assert persisted.is_active is True
        assert await db_session.scalar(select(QuestionnaireResponse)) is None
