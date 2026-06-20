"""
User accounts. Password hashing helpers live in app/auth/security.py
(thin wrapper around werkzeug.security, already a Flask dependency --
no extra crypto library needed for this).
"""

from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    # Flask-Login needs an object with this method to track the admin
    # panel's session-based login -- the JWT-based API auth doesn't use
    # this at all, only the /admin panel's own login does.
    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} is_admin={self.is_admin}>"
