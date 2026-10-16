"""Strict schemas for collaboration research artifacts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ArtifactKind = Literal[
    "research_plan",
    "questionnaire",
    "fieldnote_summary",
    "analysis_summary",
    "report_draft",
    "other",
]


class ArtifactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9_-]{0,99}$")
    kind: ArtifactKind = "other"
    title: str = Field(min_length=1, max_length=200)


class VersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    redacted_content: str = Field(min_length=1, max_length=120_000)
    redaction_status: Literal["redacted"] = "redacted"
    redaction_note: str = Field(min_length=1, max_length=2000)
    change_summary: str = Field(default="", max_length=2000)
    version_number: int | None = Field(default=None, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class AnnotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)
    anchor_start: int | None = Field(default=None, ge=0)
    anchor_end: int | None = Field(default=None, ge=0)

    @field_validator("anchor_end")
    @classmethod
    def end_requires_valid_range(cls, value: int | None, info):
        start = info.data.get("anchor_start")
        if value is not None and start is not None and value < start:
            raise ValueError("anchor_end must be greater than or equal to anchor_start")
        return value


class ReviewTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_profile_id: int | None = Field(default=None, gt=0)
    request_note: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "changes_requested", "rejected"]
    decision_note: str = Field(default="", max_length=2000)


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audience: str = Field(default="", max_length=200)
    expires_minutes: int = Field(default=60, ge=5, le=10_080)


class ShareResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_token: str = Field(min_length=20, max_length=512)
