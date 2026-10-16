"""Analysis result ownership regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_analysis import analysis_run, analysis_summary
from app.models.survey import AnalysisResult, SurveyProject, UserProfile
from app.models.user import UserAccount


async def _current_profile(db_session):
    return await db_session.scalar(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )


async def _foreign_analysis(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    project = SurveyProject(profile_id=profile.id, title="foreign analysis project")
    db_session.add(project)
    await db_session.flush()
    analysis = AnalysisResult(
        project_id=project.id,
        analysis_type="thematic",
        content="private foreign analysis",
    )
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)
    return project, analysis


class TestAnalysisOwnership:
    @pytest.mark.asyncio
    async def test_summary_hides_foreign_results(self, client, db_session):
        _, analysis = await _foreign_analysis(db_session)

        response = await client.get("/api/v1/analysis/summary")

        assert response.json()["total_analyses"] == 0
        assert all(item["id"] != analysis.id for item in response.json()["recent"])

    @pytest.mark.asyncio
    async def test_run_rejects_foreign_project_before_ai_call(
        self,
        client,
        db_session,
    ):
        project, _ = await _foreign_analysis(db_session)
        ai = AsyncMock()

        result = await analysis_run(
            payload={
                "project_id": project.id,
                "content": "private source content",
            },
            ai=ai,
            db=db_session,
            profile=await _current_profile(db_session),
        )

        assert result == {"error": "Project not found"}
        ai.chat.assert_not_awaited()
        assert await db_session.scalar(
            select(AnalysisResult).where(
                AnalysisResult.content == "private source content"
            )
        ) is None

    @pytest.mark.asyncio
    async def test_current_project_can_run_analysis(self, client, db_session):
        profile = await _current_profile(db_session)
        project = SurveyProject(profile_id=profile.id, title="owned analysis project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        ai = AsyncMock()
        ai.chat.return_value = "owned analysis"

        result = await analysis_run(
            payload={
                "project_id": project.id,
                "content": "owned source content",
            },
            ai=ai,
            db=db_session,
            profile=profile,
        )

        assert result["analysis"] == "owned analysis"
        assert await db_session.scalar(
            select(AnalysisResult).where(
                AnalysisResult.project_id == project.id,
                AnalysisResult.content == "owned analysis",
            )
        ) is not None
