"""Collaboration artifact, review, and redacted-share boundary tests."""

from sqlalchemy import select

from app.models.research_artifact import ResearchArtifactVersion


async def _create_project(client):
    response = await client.post(
        "/api/v1/projects",
        json={"title": "协作研究测试", "research_direction": "社区参与", "paradigm": "qualitative"},
    )
    assert response.status_code == 200
    return response.json()["id"]


async def _create_artifact_version(client):
    project_id = await _create_project(client)
    artifact_response = await client.post(
        f"/api/v1/collaboration/projects/{project_id}/artifacts",
        json={"artifact_key": "fieldnote-summary", "kind": "fieldnote_summary", "title": "脱敏田野摘要"},
    )
    assert artifact_response.status_code == 201
    artifact_id = artifact_response.json()["artifact"]["id"]
    version_response = await client.post(
        f"/api/v1/collaboration/artifacts/{artifact_id}/versions",
        json={
            "redacted_content": "受访者以 R1 代称；摘要仅保留主题和方法，不含直接身份信息。",
            "redaction_note": "已去除姓名、联系方式和可直接定位的细节。",
            "change_summary": "初版脱敏摘要",
            "idempotency_key": "artifact-version-1",
        },
    )
    assert version_response.status_code == 201
    return project_id, artifact_id, version_response.json()["version"]["id"]


async def test_artifact_review_and_share_lifecycle(client):
    project_id, artifact_id, version_id = await _create_artifact_version(client)

    annotation = await client.post(
        f"/api/v1/collaboration/versions/{version_id}/annotations",
        json={"body": "请补充抽样边界的说明。", "anchor_start": 0, "anchor_end": 5},
    )
    assert annotation.status_code == 201

    task = await client.post(
        f"/api/v1/collaboration/versions/{version_id}/review-tasks",
        json={"request_note": "请复核脱敏和方法说明。"},
    )
    assert task.status_code == 201
    task_id = task.json()["review_task"]["id"]
    assert task.json()["review_task"]["status"] == "pending"

    decision = await client.post(
        f"/api/v1/collaboration/review-tasks/{task_id}/decision",
        json={"status": "approved", "decision_note": "脱敏范围可接受。"},
    )
    assert decision.status_code == 200
    assert decision.json()["review_task"]["status"] == "approved"

    share = await client.post(
        f"/api/v1/collaboration/versions/{version_id}/shares",
        json={"audience": "研究小组", "expires_minutes": 30},
    )
    assert share.status_code == 201
    share_data = share.json()
    assert share_data["share_token"]
    assert "share_token" not in share_data["share"]

    resolved = await client.post(
        "/api/v1/collaboration/shares/resolve",
        json={"share_token": share_data["share_token"]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["share_scope"] == "redacted_version_only"
    assert "R1" in resolved.json()["version"]["redacted_content"]

    revoked = await client.post(
        f"/api/v1/collaboration/shares/{share_data['share']['id']}/revoke"
    )
    assert revoked.status_code == 200
    expired = await client.post(
        "/api/v1/collaboration/shares/resolve",
        json={"share_token": share_data["share_token"]},
    )
    assert expired.status_code == 404

    artifacts = await client.get(f"/api/v1/collaboration/projects/{project_id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()["artifacts"][0]["id"] == artifact_id


async def test_artifact_version_idempotency_reuses_existing_version(client, db_session):
    _, artifact_id, version_id = await _create_artifact_version(client)
    duplicate = await client.post(
        f"/api/v1/collaboration/artifacts/{artifact_id}/versions",
        json={
            "redacted_content": "另一份内容不会覆盖已提交的版本。",
            "redaction_note": "已完成脱敏。",
            "idempotency_key": "artifact-version-1",
        },
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["created"] is False
    assert duplicate.json()["version"]["id"] == version_id
    versions = (
        await db_session.execute(
            select(ResearchArtifactVersion).where(ResearchArtifactVersion.artifact_id == artifact_id)
        )
    ).scalars().all()
    assert len(versions) == 1

    second = await client.post(
        f"/api/v1/collaboration/artifacts/{artifact_id}/versions",
        json={
            "redacted_content": "第二个脱敏版本。",
            "redaction_note": "继续去除直接身份信息。",
            "idempotency_key": "artifact-version-2",
        },
    )
    assert second.status_code == 201
    page = await client.get(
        f"/api/v1/collaboration/artifacts/{artifact_id}/versions?limit=1"
    )
    assert page.status_code == 200
    assert page.json()["pagination"]["has_more"] is True


async def test_artifact_rejects_obvious_direct_identifiers(client):
    project_id = await _create_project(client)
    artifact_response = await client.post(
        f"/api/v1/collaboration/projects/{project_id}/artifacts",
        json={"artifact_key": "unsafe", "title": "不安全内容"},
    )
    artifact_id = artifact_response.json()["artifact"]["id"]
    for content in ("email: person@example.com", "api_key=secret-value", "手机号 13812345678"):
        response = await client.post(
            f"/api/v1/collaboration/artifacts/{artifact_id}/versions",
            json={"redacted_content": content, "redaction_note": "未完成"},
        )
        assert response.status_code == 422
