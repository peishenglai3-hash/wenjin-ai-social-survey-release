"""Library project ownership regression tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api.v1.router_library import generate_lessons
from app.models.survey import SurveyProject, UserProfile
from app.models.user import UserAccount


async def _foreign_project(db_session):
    foreign_profile = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign_profile)
    await db_session.flush()
    project = SurveyProject(profile_id=foreign_profile.id, title="foreign library project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


class TestLibraryOwnership:
    @pytest.mark.asyncio
    async def test_list_hides_foreign_projects(self, client, db_session):
        project = await _foreign_project(db_session)

        response = await client.get("/api/v1/library")

        assert response.status_code == 200
        assert all(item["id"] != project.id for item in response.json()["projects"])

    @pytest.mark.asyncio
    async def test_detail_and_delete_do_not_cross_project_boundary(
        self,
        client,
        db_session,
    ):
        project = await _foreign_project(db_session)

        detail = await client.get(f"/api/v1/library/{project.id}")
        deleted = await client.delete(f"/api/v1/library/{project.id}")

        assert detail.json() == {"error": "Project not found"}
        assert deleted.json() == {"error": "Project not found"}
        persisted = await db_session.scalar(
            select(SurveyProject).where(SurveyProject.id == project.id)
        )
        assert persisted is not None

    @pytest.mark.asyncio
    async def test_lessons_does_not_send_foreign_project_to_ai(self, client, db_session):
        project = await _foreign_project(db_session)
        ai = AsyncMock()

        result = await generate_lessons(
            project.id,
            ai=ai,
            db=db_session,
            profile=await client_profile(db_session),
        )

        assert result == {"error": "Project not found"}
        ai.chat.assert_not_awaited()


async def client_profile(db_session):
    result = await db_session.execute(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )
    return result.scalar_one()
