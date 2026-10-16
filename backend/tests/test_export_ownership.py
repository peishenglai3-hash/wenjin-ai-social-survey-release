"""Export document ownership regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_export import export_generate
from app.models.survey import ExportDocument, SurveyProject, UserProfile
from app.models.user import UserAccount


async def _current_profile(db_session):
    return await db_session.scalar(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )


async def _foreign_export(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    project = SurveyProject(profile_id=profile.id, title="foreign export project")
    db_session.add(project)
    await db_session.flush()
    document = ExportDocument(
        project_id=project.id,
        format_type="report",
        content="private foreign export",
    )
    db_session.add(document)
    await db_session.commit()
    await db_session.refresh(document)
    return project, document


class TestExportOwnership:
    @pytest.mark.asyncio
    async def test_foreign_export_cannot_be_downloaded(self, client, db_session):
        _, document = await _foreign_export(db_session)

        response = await client.get(f"/api/v1/export/download/{document.id}")

        assert response.json() == {"error": "Export not found"}

    @pytest.mark.asyncio
    async def test_generate_rejects_foreign_project_before_ai_call(
        self,
        client,
        db_session,
    ):
        project, _ = await _foreign_export(db_session)
        ai = AsyncMock()

        result = await export_generate(
            payload={
                "project_id": project.id,
                "content": "private source content",
                "format": "report",
            },
            ai=ai,
            db=db_session,
            profile=await _current_profile(db_session),
        )

        assert result == {"error": "Project not found"}
        ai.chat.assert_not_awaited()
        assert await db_session.scalar(select(ExportDocument).where(
            ExportDocument.content == "private source content"
        )) is None

    @pytest.mark.asyncio
    async def test_current_project_can_generate_export(self, client, db_session):
        profile = await _current_profile(db_session)
        project = SurveyProject(profile_id=profile.id, title="owned export project")
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        ai = AsyncMock()
        ai.chat.return_value = "generated export"

        result = await export_generate(
            payload={
                "project_id": project.id,
                "content": "owned source content",
                "format": "report",
            },
            ai=ai,
            db=db_session,
            profile=profile,
        )

        assert result["output"] == "generated export"
        assert await db_session.scalar(
            select(ExportDocument).where(
                ExportDocument.project_id == project.id,
                ExportDocument.content == "generated export",
            )
        ) is not None
