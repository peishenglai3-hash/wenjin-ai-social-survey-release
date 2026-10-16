"""Project collaboration metadata.

V1 stores membership and review/audit metadata separately from the stable
single-researcher artifact tables. No transcript, audio, or raw respondent
content is copied into these records.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "profile_id", name="uq_project_member_project_profile"),
        Index("ix_project_members_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id", ondelete="CASCADE"), nullable=False,
    )
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    status: Mapped[str] = mapped_column(String(20), default="active")
    invited_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True,
    )


class ProjectInvitation(Base, TimestampMixin):
    __tablename__ = "project_invitations"
    __table_args__ = (
        Index("ix_project_invitations_invitee_status", "invitee_profile_id", "status"),
        Index("ix_project_invitations_project_status", "project_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id", ondelete="CASCADE"), nullable=False,
    )
    invitee_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    inviter_profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), default="viewer")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ProjectAuditEvent(Base, TimestampMixin):
    __tablename__ = "project_audit_events"
    __table_args__ = (
        Index("ix_project_audit_events_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("survey_projects.id", ondelete="CASCADE"), nullable=False,
    )
    actor_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), default="project")
    target_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

