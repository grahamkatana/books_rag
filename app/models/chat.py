"""
Chat history models.

A Chat is one conversation thread, holding many Messages in order. Each
assistant Message can have multiple Citations -- one row per
<CITATION>...</CITATION> tag found in its content, resolved back to a
Book where possible.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.book import Book


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nullable so chats created via the CLI (no logged-in user involved)
    # keep working -- only chats created through the authenticated API
    # get a real owner.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )

    def __repr__(self) -> str:
        return f"<Chat id={self.id} title={self.title!r}>"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id"), nullable=False)

    role: Mapped[str] = mapped_column(String, nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    chat: Mapped["Chat"] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="Citation.order_index",
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role!r}>"


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), nullable=False)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id"), nullable=True)

    # The exact text that was inside <CITATION>...</CITATION> in the answer,
    # e.g. "(Sommerville, 2011, p. 47)" or '(Moffat, 2026, "Positioning
    # Risk-First Software Development" section)'.
    apa_text: Mapped[str] = mapped_column(String, nullable=False)

    # Raw locator carried separately too, for frontend use without needing
    # to parse apa_text back apart, e.g. "p. 47" or "Stage 1: Specification".
    locator: Mapped[str | None] = mapped_column(String, nullable=True)

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    message: Mapped["Message"] = relationship(back_populates="citations")
    book: Mapped["Book | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Citation id={self.id} apa_text={self.apa_text!r}>"
