"""
Models for the document-verification feature: upload a .docx, extract
its checkable claims, verify each one against the existing book/paper
corpus (and Brave Search as a fallback), and annotate the result.

Four tables, each existing for a clear reason rather than being
collapsed into fewer, wider ones:

VerificationDocument -- one row per uploaded file. Tracks status
through the pipeline (converting -> extracting claims -> verifying ->
done) so the frontend can poll a single thing and show real progress,
not just "done or not."

ExtractedClaim -- one row per checkable statement the extraction agent
found in the document, in document order. Deliberately NOT every
sentence: the extraction agent's whole job is filtering out opinion,
transitions, and non-factual prose before this table is ever written to.

ClaimVerification -- one row per claim's verdict. A separate table from
ExtractedClaim (rather than columns bolted onto it) because extraction
and verification are genuinely separate pipeline stages that can fail
or be retried independently -- a claim can exist with no verification
yet (still queued), which a single merged table would represent
awkwardly as a bunch of nullable columns.

ClaimEvidence -- one or more rows per verification, the actual sources
that produced the verdict. Mirrors Citation's book_id/paper_id
mutual-exclusivity pattern exactly (same ondelete="SET NULL"
reasoning -- evidence should survive a source's later deletion, not
disappear or block it), plus a web_url/web_title pair for when Brave
Search was the source instead of the existing corpus, since a claim's
evidence isn't guaranteed to come from material already ingested.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.book import Book
from app.models.paper import Paper


class VerificationDocument(Base):
    __tablename__ = "verification_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    filename: Mapped[str] = mapped_column(String, nullable=False)
    markdown: Mapped[str | None] = mapped_column(Text, nullable=True)  # set once Docling conversion succeeds

    # "uploaded" -> "converting" -> "extracting_claims" -> "verifying" -> "done" | "failed"
    # -- a plain string, not an Enum column: this list will grow as the
    # pipeline gets richer, and a string avoids a migration every time
    # a new intermediate stage gets added.
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    claims: Mapped[list["ExtractedClaim"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="ExtractedClaim.order_index",
    )

    def __repr__(self) -> str:
        return f"<VerificationDocument id={self.id} filename={self.filename!r} status={self.status!r}>"


class ExtractedClaim(Base):
    __tablename__ = "extracted_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("verification_documents.id"), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document: Mapped["VerificationDocument"] = relationship(back_populates="claims")
    verification: Mapped["ClaimVerification | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False,
    )

    def __repr__(self) -> str:
        return f"<ExtractedClaim id={self.id} text={self.text[:50]!r}>"


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # One verification per claim -- unique, not just indexed, since this
    # is genuinely a one-to-one relationship (a claim gets re-verified by
    # overwriting/replacing this row, not by accumulating several).
    claim_id: Mapped[int] = mapped_column(ForeignKey("extracted_claims.id"), nullable=False, unique=True)

    verdict: Mapped[str] = mapped_column(String, nullable=False)  # supported | partially_supported | contradicted | unverifiable
    confidence: Mapped[str] = mapped_column(String, nullable=False)  # high | medium | low
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    claim: Mapped["ExtractedClaim"] = relationship(back_populates="verification")
    evidence: Mapped[list["ClaimEvidence"]] = relationship(
        back_populates="verification",
        cascade="all, delete-orphan",
        order_by="ClaimEvidence.order_index",
    )

    def __repr__(self) -> str:
        return f"<ClaimVerification id={self.id} verdict={self.verdict!r} confidence={self.confidence!r}>"


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    verification_id: Mapped[int] = mapped_column(ForeignKey("claim_verifications.id"), nullable=False)

    # Mutually exclusive with web_url, same pattern Citation already
    # uses for book_id/paper_id: at most one source per evidence row,
    # and ondelete="SET NULL" so evidence survives a source's later
    # deletion rather than blocking it or vanishing silently.
    book_id: Mapped[int | None] = mapped_column(ForeignKey("books.id", ondelete="SET NULL"), nullable=True)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("papers.id", ondelete="SET NULL"), nullable=True)

    # Set instead of book_id/paper_id when Brave Search was the source
    # rather than the existing corpus -- a claim's supporting (or
    # contradicting) evidence isn't guaranteed to already be ingested.
    web_url: Mapped[str | None] = mapped_column(String, nullable=True)
    web_title: Mapped[str | None] = mapped_column(String, nullable=True)

    excerpt: Mapped[str] = mapped_column(Text, nullable=False)  # the actual retrieved text this evidence is based on
    locator: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "p. 47", same concept as Citation.locator
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    verification: Mapped["ClaimVerification"] = relationship(back_populates="evidence")
    book: Mapped["Book | None"] = relationship()
    paper: Mapped["Paper | None"] = relationship()

    def __repr__(self) -> str:
        return f"<ClaimEvidence id={self.id} book_id={self.book_id} paper_id={self.paper_id} web_url={self.web_url!r}>"