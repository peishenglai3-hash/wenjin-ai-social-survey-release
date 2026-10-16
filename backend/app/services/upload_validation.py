"""Bounded, signature-aware handling for fieldwork media uploads."""

from pathlib import Path
from typing import Protocol


UPLOAD_CHUNK_SIZE = 1024 * 1024
SUPPORTED_UPLOAD_EXTENSIONS = frozenset(
    {
        ".wav",
        ".mp3",
        ".m4a",
        ".ogg",
        ".flac",
        ".mp4",
        ".mov",
        ".mkv",
        ".aac",
        ".opus",
        ".webm",
    }
)


class AsyncReadable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


class UploadValidationError(ValueError):
    """Base class for user-correctable upload validation failures."""


class UploadTooLargeError(UploadValidationError):
    def __init__(self, size_bytes: int, max_bytes: int):
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__("uploaded file exceeds the configured size limit")


class UploadEmptyError(UploadValidationError):
    def __init__(self):
        super().__init__("uploaded file is empty")


class UploadContentError(UploadValidationError):
    def __init__(self, suffix: str):
        self.suffix = suffix
        super().__init__("uploaded content does not match its file extension")


def _looks_like_mp3(header: bytes) -> bool:
    if header.startswith(b"ID3"):
        return True
    return any(
        first == 0xFF
        and (second & 0xE0) == 0xE0
        and (second & 0x06) != 0
        for first, second in zip(header, header[1:])
    )


def _looks_like_adts_aac(header: bytes) -> bool:
    return len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF6) == 0xF0


def validate_upload_header(suffix: str, header: bytes) -> bool:
    """Return whether a bounded prefix matches a supported media container."""

    normalized = suffix.lower()
    if normalized == ".wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if normalized == ".flac":
        return header.startswith(b"fLaC")
    if normalized in {".ogg", ".opus", ".webm"}:
        return header.startswith(b"OggS") if normalized != ".webm" else header.startswith(b"\x1a\x45\xdf\xa3")
    if normalized in {".mp4", ".m4a", ".mov"}:
        return len(header) >= 8 and header[4:8] == b"ftyp"
    if normalized == ".mkv":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if normalized == ".mp3":
        return _looks_like_mp3(header)
    if normalized == ".aac":
        return _looks_like_adts_aac(header)
    return False


async def save_upload_stream(
    source: AsyncReadable,
    destination: Path,
    suffix: str,
    max_bytes: int,
) -> int:
    """Write an upload in bounded chunks and remove invalid partial files."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    prefix = bytearray()

    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await source.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                if total + len(chunk) > max_bytes:
                    raise UploadTooLargeError(total + len(chunk), max_bytes)
                if len(prefix) < 64:
                    prefix.extend(chunk[: 64 - len(prefix)])
                handle.write(chunk)
                total += len(chunk)

        if total == 0:
            raise UploadEmptyError()
        if not validate_upload_header(suffix, bytes(prefix)):
            raise UploadContentError(suffix)
        return total
    except Exception:
        destination.unlink(missing_ok=True)
        raise
