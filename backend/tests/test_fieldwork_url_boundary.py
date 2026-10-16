"""Provider URL and server-owned upload boundary tests."""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import router_fieldwork
from app.config import settings


@pytest.mark.asyncio
async def test_process_ignores_client_file_url_and_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "")
    file_id = "abc123def456"
    (tmp_path / f"{file_id}.wav").write_bytes(b"audio")

    submit = AsyncMock()
    monkeypatch.setattr(router_fieldwork.qwen_filetrans, "submit", submit)

    result = await router_fieldwork.process_transcription(
        file_id,
        {
            "file_url": "http://127.0.0.1:8000/internal-secrets",
            "language": "zh",
        },
    )

    assert result == {
        "error": "A safe HTTPS PUBLIC_BASE_URL is required before provider submission"
    }
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_builds_provider_url_from_server_owned_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "public_base_url", "https://research.example.org/")
    file_id = "abc123def456"
    (tmp_path / f"{file_id}.wav").write_bytes(b"audio")

    submit = AsyncMock(return_value="task-1")
    poll = AsyncMock(return_value={"transcription": "你好", "sentences": []})
    monkeypatch.setattr(router_fieldwork.qwen_filetrans, "submit", submit)
    monkeypatch.setattr(router_fieldwork.qwen_filetrans, "poll", poll)

    result = await router_fieldwork.process_transcription(
        file_id,
        {"file_url": "https://attacker.example/file.wav", "language": "zh"},
    )

    assert result["status"] == "completed"
    submit.assert_awaited_once_with(
        "https://research.example.org/uploads/abc123def456.wav",
        "zh",
    )
    poll.assert_awaited_once_with("task-1")
