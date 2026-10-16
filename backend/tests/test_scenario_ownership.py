"""Saved scenario designs must remain profile-scoped."""

import pytest
from sqlalchemy import select

from app.api.v1.router_scenarios import get_saved_scenario
from app.models.survey import ScenarioDesign, UserProfile
from app.models.user import UserAccount


@pytest.mark.asyncio
async def test_saved_scenario_cannot_be_read_by_another_profile(db_session, client):
    current = await db_session.scalar(
        select(UserProfile)
        .join(UserAccount, UserAccount.id == UserProfile.user_id)
        .where(UserAccount.email == "test-researcher@example.invalid")
    )
    foreign = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign)
    await db_session.flush()
    design = ScenarioDesign(
        profile_id=foreign.id,
        name="private scenario",
        full_output="private scenario details",
    )
    db_session.add(design)
    await db_session.commit()
    await db_session.refresh(design)

    result = await get_saved_scenario(design.id, profile=current, db=db_session)

    assert result == {"error": "Scenario design not found"}
