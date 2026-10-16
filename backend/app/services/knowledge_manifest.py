"""Validation gate for deployment-owned knowledge packages.

The public repository contains no corpus. A deployment may mount a package,
but runtime ingestion is allowed only when both the package and every item are
explicitly marked approved, have an audit reference, and match their recorded
hashes. This module never reads arbitrary files outside the package root.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_SOURCE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,199}$")
_PROMPT_INJECTION_RE = re.compile(
    r"(?is)"
    r"(?:ignore\s+(?:all|any|the|previous)\s+instructions?"
    r"|system\s+prompt|developer\s+message|reveal\s+(?:the\s+)?(?:system|hidden|secret)\s+prompt"
    r"|(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|private\s+key)\s*[:=]"
    r"|-----BEGIN\s+[^\n]*PRIVATE\s+KEY-----)"
)
_CARD_FIELDS = {
    "source_file",
    "source_section",
    "keywords",
    "core_concepts",
    "practical_guidelines",
    "case_studies",
    "ethical_notes",
    "cultural_knowledge",
    "applicable_scenarios",
    "confidence",
    "extracted_at",
    "language",
    "field_context",
    "method_tags",
    "material_type",
}
_CARD_LIST_FIELDS = {
    "keywords",
    "core_concepts",
    "practical_guidelines",
    "case_studies",
    "ethical_notes",
    "cultural_knowledge",
    "applicable_scenarios",
}
_CARD_TEXT_FIELDS = {"source_file", "source_section", "extracted_at"}
_MAX_CARDS_FILE_BYTES = 5 * 1024 * 1024
_MAX_CARDS_PER_FILE = 5_000
_MAX_LIST_ITEMS = 100
_MAX_TEXT_LENGTH = 4_000
_MAX_METADATA_ITEMS = 20
_MAX_METADATA_LENGTH = 200


class KnowledgeManifestError(ValueError):
    """Raised when a knowledge package cannot pass the runtime gate."""


def _validate_text(value: Any, *, field: str, max_length: int = _MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise KnowledgeManifestError(f"knowledge card field {field} must be text")
    if len(value) > max_length or "\x00" in value:
        raise KnowledgeManifestError(f"knowledge card field {field} is too large or invalid")
    if _PROMPT_INJECTION_RE.search(value):
        raise KnowledgeManifestError(f"knowledge card field {field} contains a blocked instruction or credential marker")
    return value


def _validate_relative_metadata_path(value: str, *, field: str) -> str:
    normalized = value.replace("\\", "/")
    path = Path(normalized)
    if value and (
        path.is_absolute()
        or ":" in normalized[:3]
        or normalized.startswith("/")
        or ".." in path.parts
    ):
        raise KnowledgeManifestError(f"knowledge card field {field} must be a relative metadata path")
    return normalized


def _validate_card_sequence(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list) or len(value) > _MAX_LIST_ITEMS:
        raise KnowledgeManifestError(f"knowledge card field {field} must be a bounded list")
    normalized: list[Any] = []
    for entry in value:
        if isinstance(entry, str):
            normalized.append(_validate_text(entry, field=field))
            continue
        if not isinstance(entry, dict) or len(entry) > 12:
            raise KnowledgeManifestError(f"knowledge card field {field} contains an unsupported value")
        clean_entry: dict[str, Any] = {}
        for key, nested in entry.items():
            if not isinstance(key, str) or len(key) > 80:
                raise KnowledgeManifestError(f"knowledge card field {field} contains an invalid key")
            if isinstance(nested, str):
                clean_entry[key] = _validate_text(nested, field=field)
            elif isinstance(nested, (int, float, bool)) or nested is None:
                clean_entry[key] = nested
            else:
                raise KnowledgeManifestError(f"knowledge card field {field} contains an unsupported nested value")
        normalized.append(clean_entry)
    return normalized


def validate_card_payload(card: Any, *, source_slug: str, index: int) -> dict[str, Any]:
    """Validate one approved-package card before it can reach the ORM/runtime."""
    if not isinstance(card, dict):
        raise KnowledgeManifestError(f"knowledge card {source_slug}[{index}] must be an object")
    unknown = set(card) - _CARD_FIELDS
    if unknown:
        raise KnowledgeManifestError(f"knowledge card {source_slug}[{index}] contains unsupported fields")

    normalized: dict[str, Any] = {}
    for field in _CARD_TEXT_FIELDS:
        value = card.get(field, "")
        value = _validate_text(value, field=field)
        if field == "source_file":
            value = _validate_relative_metadata_path(value, field=field)
        normalized[field] = value
    for field in _CARD_LIST_FIELDS:
        normalized[field] = _validate_card_sequence(card.get(field, []), field=field)

    confidence = card.get("confidence", 3)
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not 1 <= confidence <= 5:
        raise KnowledgeManifestError(f"knowledge card {source_slug}[{index}] has invalid confidence")
    normalized["confidence"] = confidence

    language = card.get("language", "bilingual")
    if language not in {"zh", "en", "bilingual"}:
        raise KnowledgeManifestError(f"knowledge card {source_slug}[{index}] has invalid language")
    normalized["language"] = language

    for field in ("field_context", "method_tags"):
        values = card.get(field, [])
        if not isinstance(values, list) or len(values) > _MAX_METADATA_ITEMS:
            raise KnowledgeManifestError(f"knowledge card field {field} must be a bounded list")
        normalized[field] = [
            _validate_text(value, field=field, max_length=_MAX_METADATA_LENGTH)
            for value in values
        ]

    material_type = card.get("material_type", "reference_card")
    if material_type not in {"reference_card", "training_example", "prompt_fragment"}:
        raise KnowledgeManifestError(f"knowledge card {source_slug}[{index}] has invalid material_type")
    normalized["material_type"] = material_type
    return normalized


def _read_and_validate_cards(cards_path: Path, *, source_slug: str) -> list[dict[str, Any]]:
    try:
        if cards_path.stat().st_size > _MAX_CARDS_FILE_BYTES:
            raise KnowledgeManifestError(f"cards file is too large for {source_slug}")
        raw_cards = cards_path.read_bytes()
        cards_data = json.loads(raw_cards.decode("utf-8"))
    except KnowledgeManifestError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise KnowledgeManifestError(f"cards file is not valid UTF-8 JSON for {source_slug}") from exc
    if not isinstance(cards_data, dict) or not isinstance(cards_data.get("cards"), list):
        raise KnowledgeManifestError(f"cards file has invalid structure for {source_slug}")
    cards = cards_data["cards"]
    if len(cards) > _MAX_CARDS_PER_FILE:
        raise KnowledgeManifestError(f"cards file contains too many cards for {source_slug}")
    declared_source = cards_data.get("source")
    if declared_source is not None and declared_source != source_slug:
        raise KnowledgeManifestError(f"cards source mismatch for {source_slug}")
    return [validate_card_payload(card, source_slug=source_slug, index=index) for index, card in enumerate(cards)]


class KnowledgeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_slug: str = Field(min_length=1, max_length=200)
    cards_file: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=8, max_length=1000)
    license_status: Literal["approved"]
    privacy_status: Literal["public_metadata", "redacted"]
    audit_status: Literal["approved"]
    revoked: bool = False
    content_sha256: str

    @field_validator("source_slug")
    @classmethod
    def source_slug_must_be_safe_identifier(cls, value: str) -> str:
        if not _SOURCE_SLUG_RE.fullmatch(value):
            raise ValueError("source_slug must be a lowercase metadata identifier")
        return value

    @field_validator("cards_file")
    @classmethod
    def cards_file_must_be_relative(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("cards_file must stay inside the package directory")
        return value.replace("\\", "/")

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_https(cls, value: str) -> str:
        if not (value.startswith("https://") or value.startswith("http://")):
            raise ValueError("source_url must be an http(s) URL")
        return value

    @field_validator("content_sha256")
    @classmethod
    def hash_must_be_sha256(cls, value: str) -> str:
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        return value.lower()


class KnowledgeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin-knowledge/v1"]
    package_id: str = Field(min_length=1, max_length=200)
    package_version: str = Field(min_length=1, max_length=50)
    status: Literal["approved"]
    audit_status: Literal["approved"]
    audit_report_ref: str = Field(min_length=1, max_length=500)
    approved_by: str = Field(min_length=1, max_length=200)
    approved_at: str = Field(min_length=1, max_length=80)
    items: list[KnowledgeItem] = Field(min_length=1, max_length=500)


def _safe_manifest_path(package_dir: Path, relative_path: str) -> Path:
    root = package_dir.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise KnowledgeManifestError("manifest file escapes package directory") from exc
    return candidate


def load_manifest(package_dir: str | Path) -> tuple[KnowledgeManifest, Path]:
    """Load and verify an approved manifest plus each approved card file hash."""
    root = Path(package_dir).expanduser().resolve()
    if not root.is_dir():
        raise KnowledgeManifestError("knowledge package directory does not exist")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise KnowledgeManifestError("knowledge package manifest.json is required")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = KnowledgeManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise KnowledgeManifestError("knowledge manifest is invalid") from exc

    for item in manifest.items:
        if item.revoked:
            raise KnowledgeManifestError(f"knowledge item {item.source_slug} is revoked")
        cards_path = _safe_manifest_path(root, item.cards_file)
        if not cards_path.is_file():
            raise KnowledgeManifestError(f"cards file missing for {item.source_slug}")
        try:
            if cards_path.stat().st_size > _MAX_CARDS_FILE_BYTES:
                raise KnowledgeManifestError(f"cards file is too large for {item.source_slug}")
            raw_cards = cards_path.read_bytes()
        except KnowledgeManifestError:
            raise
        except OSError as exc:
            raise KnowledgeManifestError(f"cards file cannot be read for {item.source_slug}") from exc
        digest = hashlib.sha256(raw_cards).hexdigest()
        if digest != item.content_sha256:
            raise KnowledgeManifestError(f"cards hash mismatch for {item.source_slug}")
        _read_and_validate_cards(cards_path, source_slug=item.source_slug)
    return manifest, root


def load_approved_cards(cards_path: Path, *, source_slug: str) -> list[dict[str, Any]]:
    """Read the already hash-checked card file using the same strict validator."""
    return _read_and_validate_cards(cards_path, source_slug=source_slug)


def iter_approved_items(package_dir: str | Path) -> list[tuple[KnowledgeItem, Path]]:
    """Return only verified runtime items; never glob unregistered JSON files."""
    manifest, root = load_manifest(package_dir)
    return [(item, _safe_manifest_path(root, item.cards_file)) for item in manifest.items]

