"""WISE proposal gate tests: AI candidates require explicit promotion."""

from sqlalchemy import func, select

from app.models.survey import UserMemory, UserProfile
from app.models.wise import WISEProposal


def _candidate_payload(**overrides):
    payload = {
        "kind": "candidate_memory",
        "title": "候选研究偏好",
        "proposal_text": "用户倾向先做现场语境核查，再确定分析框架。",
        "candidate_memory": {
            "category": "methodology",
            "key": "field_context_first",
            "value": "用户倾向先做现场语境核查，再确定分析框架。",
            "confidence": 0.8,
            "importance": 4,
        },
        "evidence_refs": ["reflection:session-1"],
        "confidence": 0.8,
        "idempotency_key": "wise-test-1",
    }
    payload.update(overrides)
    return payload


async def test_wise_pending_proposal_does_not_write_memory(client, db_session):
    response = await client.post("/api/v1/wise/proposals", json=_candidate_payload())
    assert response.status_code == 201
    proposal = response.json()["proposal"]
    assert proposal["status"] == "pending"

    count = await db_session.scalar(
        select(func.count(UserMemory.id)).where(UserMemory.key == "field_context_first")
    )
    assert count == 0


async def test_wise_approval_promotes_once_and_is_idempotent(client, db_session):
    response = await client.post(
        "/api/v1/wise/proposals",
        json=_candidate_payload(idempotency_key="wise-approve-1"),
    )
    proposal_id = response.json()["proposal"]["id"]

    approved = await client.post(
        f"/api/v1/wise/proposals/{proposal_id}/approve",
        json={"note": "人工核对通过"},
    )
    assert approved.status_code == 200
    assert approved.json()["saved_memory_count"] == 1
    assert approved.json()["proposal"]["status"] == "approved"

    repeated = await client.post(f"/api/v1/wise/proposals/{proposal_id}/approve", json={})
    assert repeated.status_code == 200
    assert repeated.json()["saved_memory_count"] == 0
    count = await db_session.scalar(
        select(func.count(UserMemory.id)).where(UserMemory.key == "field_context_first")
    )
    assert count == 1


async def test_wise_revoke_suppresses_promoted_memory_and_blocks_reapproval(client, db_session):
    response = await client.post(
        "/api/v1/wise/proposals",
        json=_candidate_payload(idempotency_key="wise-revoke-1"),
    )
    proposal_id = response.json()["proposal"]["id"]
    await client.post(f"/api/v1/wise/proposals/{proposal_id}/approve", json={})

    revoked = await client.post(
        f"/api/v1/wise/proposals/{proposal_id}/revoke",
        json={"note": "复核后不再适用"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["proposal"]["status"] == "revoked"

    memory = (
        await db_session.execute(
            select(UserMemory).where(UserMemory.key == "field_context_first")
        )
    ).scalar_one()
    assert memory.confidence == 0.1

    reapprove = await client.post(f"/api/v1/wise/proposals/{proposal_id}/approve", json={})
    assert reapprove.status_code == 409


async def test_wise_idempotency_reuses_owned_pending_proposal(client, db_session):
    first = await client.post(
        "/api/v1/wise/proposals",
        json=_candidate_payload(idempotency_key="wise-idempotent-1"),
    )
    second = await client.post(
        "/api/v1/wise/proposals",
        json=_candidate_payload(
            idempotency_key="wise-idempotent-1",
            title="重复提交",
            proposal_text="不应覆盖原提案",
        ),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["proposal"]["id"] == first.json()["proposal"]["id"]


async def test_wise_schema_rejects_memory_without_candidate(client):
    response = await client.post(
        "/api/v1/wise/proposals",
        json={
            "kind": "candidate_memory",
            "title": "缺少候选内容",
            "proposal_text": "invalid",
        },
    )
    assert response.status_code == 422
    assert "candidate_memory" not in response.text or "required" in response.text


async def test_wise_foreign_proposal_is_not_readable(client, db_session):
    foreign = UserProfile(user_id=None, role="researcher")
    db_session.add(foreign)
    await db_session.flush()
    proposal = WISEProposal(
        profile_id=foreign.id,
        kind="research_action",
        status="pending",
        title="foreign",
        proposal_text="foreign",
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)

    response = await client.get(f"/api/v1/wise/proposals/{proposal.id}")
    assert response.status_code == 404
