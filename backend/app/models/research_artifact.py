"""Collaboration research artifacts, versions, annotations, reviews, and shares."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ResearchArtifact(Base, TimestampMixin):
    __tablename__ = "research_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "artifact_key", name="uq_research_artifact_project_key"),
        Index("ix_research_artifacts_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_key: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class ResearchArtifactVersion(Base, TimestampMixin):
    __tablename__ = "research_artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number", name="uq_research_artifact_version_number"),
        Index("ix_research_artifact_versions_artifact_created", "artifact_id", "created_at"),
        Index("ix_research_artifact_versions_idempotency", "artifact_id", "idempotency_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    redaction_status: Mapped[str] = mapped_column(String(20), nullable=False, default="redacted")
    redacted_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    redaction_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)


class ResearchAnnotation(Base, TimestampMixin):
    __tablename__ = "research_annotations"
    __table_args__ = (Index("ix_research_annotations_version_status", "version_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    author_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    anchor_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    anchor_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    resolution_note: Mapped[str] = mapped_column(Text, nullable=False, default="")


class ResearchReviewTask(Base, TimestampMixin):
    __tablename__ = "research_review_tasks"
    __table_args__ = (Index("ix_research_review_tasks_version_status", "version_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    request_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ResearchShare(Base, TimestampMixin):
    __tablename__ = "research_shares"
    __table_args__ = (
        Index("ix_research_shares_version_status", "version_id", "status"),
        Index("ix_research_shares_expires", "expires_at", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("research_artifact_versions.id", ondelete="CASCADE"), nullable=False
    )
    created_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
