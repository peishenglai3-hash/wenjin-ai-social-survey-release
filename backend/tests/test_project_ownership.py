"""Project ownership regression tests for authenticated users."""

import pytest
from sqlalchemy import select

from app.models.survey import SurveyProject, UserProfile
from app.models.user import UserAccount


async def _current_profile(db_session):
    result = await db_session.execute(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )
    return result.scalar_one()


class TestProjectOwnership:
    @pytest.mark.asyncio
    async def test_create_ignores_foreign_profile_id(self, client, db_session):
        current_profile = await _current_profile(db_session)
        foreign_profile = UserProfile(user_id=None, role="researcher")
        db_session.add(foreign_profile)
        await db_session.commit()
        await db_session.refresh(foreign_profile)

        response = await client.post(
            "/api/v1/projects",
            json={"profile_id": foreign_profile.id, "title": "owned project"},
        )

        assert response.status_code == 200
        detail = await client.get(f"/api/v1/projects/{response.json()['id']}")
        assert detail.json()["profile_id"] == current_profile.id

    @pytest.mark.asyncio
    async def test_foreign_project_is_hidden_from_list_and_detail(
        self,
        client,
        db_session,
    ):
        foreign_profile = UserProfile(user_id=None, role="researcher")
        db_session.add(foreign_profile)
        await db_session.flush()
        foreign_project = SurveyProject(
            profile_id=foreign_profile.id,
            title="foreign project",
        )
        db_session.add(foreign_project)
        await db_session.commit()
        await db_session.refresh(foreign_project)

        listed = await client.get("/api/v1/projects")
        assert listed.status_code == 200
        assert all(item["title"] != "foreign project" for item in listed.json()["projects"])

        detail = await client.get(f"/api/v1/projects/{foreign_project.id}")
        assert detail.status_code == 200
        assert detail.json() == {"error": "Project not found"}

    @pytest.mark.asyncio
    async def test_foreign_project_cannot_be_updated(self, client, db_session):
        foreign_profile = UserProfile(user_id=None, role="researcher")
        db_session.add(foreign_profile)
        await db_session.flush()
        foreign_project = SurveyProject(
            profile_id=foreign_profile.id,
            title="foreign project",
        )
        db_session.add(foreign_project)
        await db_session.commit()
        await db_session.refresh(foreign_project)

        response = await client.put(
            f"/api/v1/projects/{foreign_project.id}",
            json={"title": "tampered"},
        )

        assert response.status_code == 200
        assert response.json() == {"error": "Project not found"}
        await db_session.refresh(foreign_project)
        assert foreign_project.title == "foreign project"
