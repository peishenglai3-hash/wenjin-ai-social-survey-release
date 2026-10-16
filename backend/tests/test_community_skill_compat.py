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
    assert detail.json()["execution_mode"] == "prompt_only"

    published = await client.post(
        "/api/v1/community/skills/publish",
        json={"skill_id": skill.id, "readme": "Safe usage notes", "compatible_models": ["fake"]},
    )
    assert published.status_code == 200
    assert published.json()["skill"]["execution_mode"] == "prompt_only"

    skill.prompt_template = "api_key=should-not-be-published"
    await db_session.commit()
    rejected = await client.post(
        "/api/v1/community/skills/publish",
        json={"skill_id": skill.id},
    )
    assert rejected.status_code == 422
