"""
Book metadata, used as the bibliographic source of truth for APA citations.

This is intentionally separate from the chunk-level metadata stored in
Qdrant (printed_page, chapter, etc.) -- that's locator data (where in the
book), while this is bibliographic data (how to cite the book itself).
PDFs don't reliably expose author/publisher/year, so this table is meant
to be reviewed and corrected by hand after seeding, not trusted blindly.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Matches the chunk payload's "source" field (PDF filename stem).
    # This is the join key between Qdrant chunk metadata and this table.
    source_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[str | None] = mapped_column(String, nullable=True)
    # True when `authors` names an editor of a reference work (e.g. an
    # encyclopedia) rather than a book's author -- APA credits these as
    # "(Ed.)" in the full reference, but omits it from in-text citations.
    is_editor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String, nullable=True)
    edition: Mapped[str | None] = mapped_column(String, nullable=True)

    # Groups multiple editions of the same underlying book together (e.g.
    # both the 8th and 9th edition of Sommerville's "Software Engineering"
    # would share a work_key). Leave null for a standalone book with no
    # other editions in the library.
    work_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # When a work_key has multiple Book rows, exactly one should be marked
    # preferred (normally the latest year) -- retrieval defaults to
    # searching only preferred editions, so older editions don't silently
    # blend into an answer unless explicitly asked for.
    is_preferred_edition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Deliberately separate from bibliography_verified: that's about
    # whether this book's title/authors/year/etc. are correct, this is
    # about whether a human specifically chose this edition over its
    # siblings. Conflating the two was a real bug -- a perfectly normal,
    # correctly-verified book would look "pinned" the moment
    # auto-resolution picked it for being the newest, permanently
    # locking out any genuinely newer edition added to the library later.
    # Only ever set True by a deliberate choice (the admin panel), never
    # implicitly by verifying a book's bibliography.
    edition_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # "labeled" (real embedded /PageLabels, exact page citations) or
    # "approximate" (no real page numbers, chapter + approx. PDF page)
    page_mode: Mapped[str] = mapped_column(String, nullable=False, default="approximate")

    # False until a human has confirmed authors/year/publisher are correct.
    # Auto-seeded values (e.g. guessed from a filename, or found via
    # Brave + LLM extraction) start False.
    bibliography_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Where the current title/authors/year/publisher/edition came from --
    # "filename_guess" (seed-books' first pass), "auto_lookup" (Brave +
    # LLM, via lookup-bibliography), or "manual" (edited in /admin).
    # Replaces what used to be tracked in book_overrides.json before that
    # file was retired in favor of writing straight to this table.
    bibliography_source: Mapped[str | None] = mapped_column(String, nullable=True)

    # Only meaningful when bibliography_source == "auto_lookup" -- the
    # LLM's own "high"/"medium"/"low" judgment of how consistent the
    # Brave search results were, set by lookup_bibliography.py.
    lookup_confidence: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Book id={self.id} source_key={self.source_key!r} verified={self.bibliography_verified}>"
