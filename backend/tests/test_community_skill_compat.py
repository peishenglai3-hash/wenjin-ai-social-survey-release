"""Regression tests for the pre-existing community skill routes."""

import pytest
from sqlalchemy import select

from app.models.survey import UserProfile, UserSkill


@pytest.mark.asyncio
async def test_community_skill_detail_and_fork_use_declared_model_fields(client, db_session):
    profile = (await db_session.execute(select(UserProfile))).scalar_one()
    skill = UserSkill(
        profile_id=profile.id,
        name="Public interview helper",
        description="A safe public example",
        prompt_template="Ask one open question",
        is_public=True,
        readme="Public README",
        compatible_models="[\"fake\"]",
    )
    db_session.add(skill)
    await db_session.commit()
    await db_session.refresh(skill)

    detail = await client.get(f"/api/v1/community/skills/{skill.id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "Public interview helper"
    assert detail.json()["compatible_models"] == '["fake"]'

    fork = await client.post(f"/api/v1/community/skills/{skill.id}/fork", json={})
    assert fork.status_code == 200
    assert fork.json()["skill"]["forked_from_id"] == skill.id
