"""Server-owned uploaded media metadata and retention boundary."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UploadedFile(Base, TimestampMixin):
    __tablename__ = "uploaded_files"
    __table_args__ = (
        Index("ix_uploaded_files_profile_expires", "profile_id", "expires_at"),
    )

    file_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False,
    )
    storage_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    suffix: Mapped[str] = mapped_column(String(12), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

