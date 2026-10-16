"""WISE proposals: reviewable innovation and memory candidates.

AI output is stored as a pending proposal first.  Only an explicit user
approval may promote a candidate memory into ``user_memories``.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WISEProposal(Base, TimestampMixin):
    """A reviewable WISE proposal owned by one profile."""

    __tablename__ = "wise_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("survey_projects.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate_memory")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    proposal_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    candidate_memory_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    evidence_refs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    applicability: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    counterexamples: Mapped[str] = mapped_column(Text, nullable=False, default="")
    side_effects: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="user")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approved_by_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="SET NULL"), nullable=True
    )
    approved_memory_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("user_memories.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_wise_proposals_profile_status", "profile_id", "status"),
        Index("ix_wise_proposals_project", "project_id"),
        Index("ix_wise_proposals_profile_idempotency", "profile_id", "idempotency_key"),
    )
