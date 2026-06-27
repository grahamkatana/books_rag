"""
Tracks whether the corpus actually "knows" what each book and paper is
about -- the formalized version of the manual sense-check an admin
already does by hand: ask "what's this about?" and judge whether the
answer makes sense. This exists because ingestion can "succeed" with
no error at all and still produce a source that's effectively useless
-- a PDF that failed to chunk meaningfully, a near-empty file, a book
that embedded as mostly garbled OCR text. None of that shows up as a
pipeline failure; the only way to actually notice is to ask the corpus
about itself, the same way a person checking by hand would.

One row per book or paper that's been checked (see
scripts/check_corpus_context.py, which is what actually writes these).
book_id/paper_id mirror Citation's own mutually-exclusive pattern
exactly -- real foreign keys the database understands, not a
polymorphic type+id pair, and ondelete="SET NULL" for the same reason
Citation uses it: deleting a Book or Paper should never be blocked by,
or cascade through, a row that exists purely to help decide whether to
delete it in the first place.

context_known is the LLM's raw judgment from the last check.
marked_for_delete is a separate, deliberately distinct column: the
script sets it to match context_known's negation as a starting
recommendation, but it stays independently editable by an admin
reviewing the flagged list -- the actual decision to delete something
is a human one, this table only ever proposes candidates.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.book import Book
from app.models.paper import Paper


class CorpusContextCheck(Base):
    __tablename__ = "corpus_context_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)

    context_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    marked_for_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    checked_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    book: Mapped["Book | None"] = relationship()
    paper: Mapped["Paper | None"] = relationship()

    def __repr__(self) -> str:
        target = f"book_id={self.book_id}" if self.book_id else f"paper_id={self.paper_id}"
        return f"<CorpusContextCheck {target} context_known={self.context_known} marked_for_delete={self.marked_for_delete}>"