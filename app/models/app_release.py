"""
Published versions of the Android app. The APK itself is stored in the
database (so it is backed up with everything else and needs no extra
volume), in its own table so listing releases never reads megabytes.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AppRelease(Base):
    """One published version. Every version is kept."""

    __tablename__ = "app_releases"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_name: Mapped[str] = mapped_column(String(40), nullable=False)  # what people read: "0.1.0"
    # What Android compares to decide which install is newer; higher = newer.
    version_code: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class AppReleaseFile(Base):
    __tablename__ = "app_release_files"

    release_id: Mapped[int] = mapped_column(ForeignKey("app_releases.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
