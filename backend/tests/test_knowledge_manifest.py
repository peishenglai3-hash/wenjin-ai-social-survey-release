"""Knowledge package approval and runtime-ingestion gate tests."""

import hashlib
import json

import pytest

from app.config import settings
from app.models.knowledge_card import ReferenceCard
from app.services.knowledge_ingestion import ingest_all
from app.services.knowledge_manifest import KnowledgeManifestError, iter_approved_items


def _write_package(tmp_path, *, status="approved", content=b'{"source":"demo","cards":[]}'):
    cards_path = tmp_path / "demo_cards.json"
    cards_path.write_bytes(content)
    manifest = {
        "schema_version": "wenjin-knowledge/v1",
        "package_id": "test-package",
        "package_version": "2026.10.16",
        "status": status,
        "audit_status": "approved",
        "audit_report_ref": "private-audit-report",
        "approved_by": "project-owner",
        "approved_at": "2026-10-16T00:00:00Z",
        "items": [
            {
                "source_slug": "demo",
                "cards_file": "demo_cards.json",
                "source_url": "https://example.invalid/demo",
                "license_status": "approved",
                "privacy_status": "redacted",
                "audit_status": "approved",
                "revoked": False,
                "content_sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cards_path


def test_manifest_rejects_unapproved_package(tmp_path):
    _write_package(tmp_path, status="needs_review")

    with pytest.raises(KnowledgeManifestError):
        iter_approved_items(tmp_path)


def test_manifest_rejects_hash_mismatch(tmp_path):
    cards_path = _write_package(tmp_path)
    cards_path.write_text('{"source":"tampered","cards":[]}', encoding="utf-8")

    with pytest.raises(KnowledgeManifestError):
        iter_approved_items(tmp_path)


def test_manifest_rejects_non_card_json(tmp_path):
    content = b'{"source":"demo","unexpected":[]}'
    _write_package(tmp_path, content=content)

    with pytest.raises(KnowledgeManifestError):
        iter_approved_items(tmp_path)


@pytest.mark.asyncio
async def test_ingestion_requires_manifest_and_does_not_glob_public_files(db_session, monkeypatch, tmp_path):
    (tmp_path / "unregistered_cards.json").write_text(
        '{"source":"unregistered","cards":[{"title":"should not load"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_dir", "")

    result = await ingest_all(db_session)

    assert result["status"] == "manifest_required"
    assert result["total_cards"] == 0
    assert (await db_session.execute(ReferenceCard.__table__.select())).all() == []


@pytest.mark.asyncio
async def test_approved_manifest_is_the_only_ingestion_source(db_session, monkeypatch, tmp_path):
    content = json.dumps(
        {
            "source": "demo",
            "cards": [
                {
                    "source_file": "metadata-only",
                    "keywords": ["interview"],
                    "practical_guidelines": ["ask an open question"],
                    "ethical_notes": ["obtain consent"],
                }
            ],
        }
    ).encode("utf-8")
    _write_package(tmp_path, content=content)
    (tmp_path / "unregistered_cards.json").write_text(
        '{"source":"unregistered","cards":[{"source_file":"private"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "knowledge_dir", str(tmp_path))

    result = await ingest_all(db_session)

    assert result["status"] == "ok"
    assert result["cards_ingested"] == 1
    rows = (await db_session.execute(ReferenceCard.__table__.select())).all()
    assert len(rows) == 1
    assert rows[0].source_slug == "demo"


@pytest.mark.asyncio
async def test_ingestion_endpoint_requires_admin(client):
    response = await client.post("/api/v1/reminders/ingest")

    assert response.status_code == 403
