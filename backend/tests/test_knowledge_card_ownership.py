"""Knowledge card ownership regression tests."""

import pytest
from sqlalchemy import select

from app.models.survey import KnowledgeCard, UserProfile


async def _foreign_card(db_session):
    profile = UserProfile(user_id=None, role="researcher")
    db_session.add(profile)
    await db_session.flush()
    card = KnowledgeCard(
        profile_id=profile.id,
        category="methodology",
        title="foreign card",
        content="private foreign content",
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


class TestKnowledgeCardOwnership:
    @pytest.mark.asyncio
    async def test_foreign_card_cannot_be_read_reused_or_deleted(self, client, db_session):
        card = await _foreign_card(db_session)

        detail = await client.get(f"/api/v1/knowledge/cards/{card.id}")
        reused = await client.post(f"/api/v1/knowledge/cards/{card.id}/reuse")
        deleted = await client.delete(f"/api/v1/knowledge/cards/{card.id}")

        assert detail.json() == {"error": "Card not found"}
        assert reused.json() == {"error": "Card not found"}
        assert deleted.json() == {"error": "Card not found"}
        persisted = await db_session.scalar(
            select(KnowledgeCard).where(KnowledgeCard.id == card.id)
        )
        assert persisted is not None
        assert persisted.reuse_count == 0

    @pytest.mark.asyncio
    async def test_current_profile_card_remains_operational(self, client, db_session):
        profile = await db_session.scalar(
            select(UserProfile).where(UserProfile.user_id.is_not(None))
        )
        card = KnowledgeCard(
            profile_id=profile.id,
            category="methodology",
            title="owned card",
            content="owned content",
        )
        db_session.add(card)
        await db_session.commit()
        await db_session.refresh(card)

        detail = await client.get(f"/api/v1/knowledge/cards/{card.id}")
        reused = await client.post(f"/api/v1/knowledge/cards/{card.id}/reuse")

        assert detail.status_code == 200
        assert detail.json()["title"] == "owned card"
        assert reused.json()["reuse_count"] == 1
