"""Streaming upload validation tests."""

from pathlib import Path

import pytest

from app.services.upload_validation import (
    UploadContentError,
    UploadEmptyError,
    UploadTooLargeError,
    save_upload_stream,
    validate_upload_header,
)


class AsyncReader:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        end = len(self._data) if size < 0 else self._offset + size
        chunk = self._data[self._offset:end]
        self._offset = end
        return chunk


@pytest.mark.parametrize(
    ("suffix", "header"),
    [
        (".wav", b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE"),
        (".flac", b"fLaC"),
        (".ogg", b"OggS"),
        (".mp3", b"ID3"),
        (".m4a", b"\x00\x00\x00\x18ftypM4A "),
        (".mkv", b"\x1a\x45\xdf\xa3"),
        (".aac", b"\xff\xf1\x50\x80"),
    ],
)
def test_accepts_known_upload_signatures(suffix, header):
    assert validate_upload_header(suffix, header) is True


def test_rejects_signature_mismatch():
    assert validate_upload_header(".wav", b"not-a-wave") is False


@pytest.mark.asyncio
async def test_save_upload_stream_writes_in_bounded_chunks(tmp_path: Path):
    destination = tmp_path / "recording.wav"
    body = b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"x" * 100

    size = await save_upload_stream(
        AsyncReader(body), destination, ".wav", max_bytes=1024
    )

    assert size == len(body)
    assert destination.read_bytes() == body


@pytest.mark.asyncio
async def test_save_upload_stream_removes_oversized_file(tmp_path: Path):
    destination = tmp_path / "recording.wav"

    with pytest.raises(UploadTooLargeError):
        await save_upload_stream(
            AsyncReader(b"RIFF" + b"\x00\x00\x00\x00" + b"WAVE" + b"x" * 100),
            destination,
            ".wav",
            max_bytes=12,
        )

    assert not destination.exists()


@pytest.mark.asyncio
async def test_save_upload_stream_removes_empty_file(tmp_path: Path):
    destination = tmp_path / "empty.wav"

    with pytest.raises(UploadEmptyError):
        await save_upload_stream(AsyncReader(b""), destination, ".wav", max_bytes=1024)

    assert not destination.exists()


@pytest.mark.asyncio
async def test_save_upload_stream_removes_signature_mismatch(tmp_path: Path):
    destination = tmp_path / "recording.wav"

    with pytest.raises(UploadContentError):
        await save_upload_stream(
            AsyncReader(b"not-a-wave"), destination, ".wav", max_bytes=1024
        )

    assert not destination.exists()
