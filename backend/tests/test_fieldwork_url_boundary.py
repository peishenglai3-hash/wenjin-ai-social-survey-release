"""Provider URL and server-owned upload boundary tests."""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import router_fieldwork
from app.config import settings


class NamedUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        end = len(self._data) if size < 0 else self._offset + size
        chunk = self._data[self._offset:end]
        self._offset = end
        return chunk


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


@pytest.mark.asyncio
async def test_upload_route_streams_and_validates_media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(router_fieldwork.qwen_filetrans, "api_key", "")
    audio = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"x" * 100

    result = await router_fieldwork.transcribe_uploaded_file(
        file=NamedUpload("interview.wav", audio),
        db=None,
    )

    assert result["status"] == "saved"
    assert result["api_key_ready"] is False
    assert len(list(tmp_path.glob("*.wav"))) == 1


@pytest.mark.asyncio
async def test_upload_route_rejects_content_extension_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    result = await router_fieldwork.transcribe_uploaded_file(
        file=NamedUpload("interview.wav", b"not-a-wave"),
        db=None,
    )

    assert result == {"error": "Uploaded content does not match its file extension"}
    assert list(tmp_path.iterdir()) == []
