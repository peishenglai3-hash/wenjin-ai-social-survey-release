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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class KnowledgeManifestError(ValueError):
    """Raised when a knowledge package cannot pass the runtime gate."""


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
        raw_cards = cards_path.read_bytes()
        try:
            cards_data = json.loads(raw_cards.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise KnowledgeManifestError(f"cards file is not valid UTF-8 JSON for {item.source_slug}") from exc
        if not isinstance(cards_data, dict) or not isinstance(cards_data.get("cards"), list):
            raise KnowledgeManifestError(f"cards file has invalid structure for {item.source_slug}")
        declared_source = cards_data.get("source")
        if declared_source is not None and declared_source != item.source_slug:
            raise KnowledgeManifestError(f"cards source mismatch for {item.source_slug}")
        digest = hashlib.sha256(raw_cards).hexdigest()
        if digest != item.content_sha256:
            raise KnowledgeManifestError(f"cards hash mismatch for {item.source_slug}")
    return manifest, root


def iter_approved_items(package_dir: str | Path) -> list[tuple[KnowledgeItem, Path]]:
    """Return only verified runtime items; never glob unregistered JSON files."""
    manifest, root = load_manifest(package_dir)
    return [(item, _safe_manifest_path(root, item.cards_file)) for item in manifest.items]

