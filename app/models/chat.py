"""
Chat history models.

A Chat is one conversation thread, holding many Messages in order. Each
assistant Message can have multiple Citations -- one row per
<CITATION>...</CITATION> tag found in its content, resolved back to a
Book or a Paper where possible (never both -- the two FKs are mutually
exclusive, enforced by the write path in app/retrieval/query_engine.py
and app/retrieval/citations.py, not a DB constraint).
"""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.book import Book
from app.models.paper import Paper


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nullable so chats created via the CLI (no logged-in user involved)
    # keep working -- only chats created through the authenticated API
    # get a real owner. ondelete="SET NULL": deleting a user (see
    # app/api/v1/admin_users.py) must orphan their chats the same way a
    # CLI-created chat already is, not block the delete (the database's
    # default) or destroy that chat's history just because its owner's
    # account was removed.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
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
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    # Mutually exclusive with book_id -- a citation comes from exactly
    # one corpus. Both nullable (rather than, say, a single polymorphic
    # "source_type" + "source_id" pair) so each keeps a real, normal
    # foreign key that the database and the ORM both understand and can
    # validate -- joining straight to Book or Paper, no manual dispatch
    # on a type string required anywhere this gets queried.
    #
    # ondelete="SET NULL" on both: deleting a Book or Paper (see
    # app/ingestion/delete_book.py / delete_paper.py) must null out any
    # existing citation's reference to it rather than block the delete
    # (the database's own default) or cascade into deleting the
    # Message/Chat that citation belongs to (which would silently wipe
    # someone's chat history just because a source was removed -- far
    # more destructive than warranted). The citation's own apa_text and
    # locator survive untouched either way, preserved as a historical
    # record of what was cited even after the source itself is gone.
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)

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
    paper: Mapped["Paper | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Citation id={self.id} apa_text={self.apa_text!r}>"