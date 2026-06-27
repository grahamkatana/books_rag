"""
A research paper, ingested via the (separate, Docling-based) papers
pipeline. Deliberately not a subclass of or merged with Book -- papers
and books are different artifacts with different identification
(DOI vs. ISBN/filename), different structure (sections vs. chapters),
and will end up in a separate Qdrant collection specifically so the two
corpora never blend together at retrieval time.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Matches the Qdrant chunk payload's "source" field, same join-key
    # role source_key plays for Book -- the PDF filename without ".pdf".
    source_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    title: Mapped[str] = mapped_column(String, nullable=False)

    # Papers routinely have several authors -- stored as one delimited
    # string for now (e.g. "Becker, F.; Sergeyuk, A.; Titov, A."),
    # consistent with how Book.authors already handles multi-author
    # books. Revisit as a separate normalized table only if a real need
    # for per-author querying shows up.
    authors: Mapped[str | None] = mapped_column(String, nullable=True)

    year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The papers' rough analog of Book.publisher -- a journal name,
    # conference proceedings, or "arXiv preprint" when unpublished.
    venue: Mapped[str | None] = mapped_column(String, nullable=True)

    # A real, structured, queryable identifier -- this is the whole
    # reason papers get DOI-based lookup (Crossref/Semantic Scholar)
    # instead of search-and-extract: DOIs resolve to one specific,
    # verifiable record, unlike a filename guess or a web search snippet.
    doi: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)

    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Same verification semantics as Book: False until a human (or a
    # successful DOI resolution against a real bibliographic record) has
    # confirmed this data, with bibliography_source recording where the
    # current values came from ("filename_guess" / "doi_lookup" /
    # "web_search" / "manual").
    bibliography_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bibliography_source: Mapped[str | None] = mapped_column(String, nullable=True)
    # Only meaningful for bibliography_source="web_search" -- DOI
    # resolution is deterministic (Crossref either has the exact record
    # or it doesn't, no judgment call involved), but the web-search
    # fallback for non-DOI sources (industry reports, white papers --
    # anything Crossref's registry was never going to have regardless
    # of how the title search is worded) is LLM-extracted from search
    # snippets, the same kind of judgment call Book.lookup_confidence
    # already exists to record.
    lookup_confidence: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<Paper id={self.id} source_key={self.source_key!r} doi={self.doi!r}>"