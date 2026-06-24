"""
Verifies every claim extracted for a document and marks it done. The
last stage of the verification pipeline, after extraction
(app/agents/extract_claims.py) -- run_verification() (verify_claim.py)
already handles one claim at a time; this just calls it for every
claim belonging to a document, in order.

Sequential, deliberately, not concurrent: each claim already costs an
embedding call, a Qdrant search, and an LLM call (sometimes two, if the
agent reaches for its web-search tool) -- running many of those at once
would be faster but adds real complexity (rate-limit pressure, DB
connection-pool pressure) for a feature that doesn't need to be fast
yet, just correct. Bounded concurrency is a contained, easy upgrade
later if latency on long documents actually becomes a problem; nothing
about this function's interface would need to change to add it.

A few individual claims failing to verify (run_verification() returning
False -- it never raises) does not fail the document as a whole: the
document still reaches "done", since the pipeline genuinely did finish
running. Which specific claims succeeded or failed is already visible
per-claim (a claim with no .verification simply has none) without
needing a separate status value for "some claims didn't verify."
"""

from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.agents.verify_claim import run_verification
from app.logging_config import get_logger

logger = get_logger(__name__)


def verify_document_claims(document_id: int) -> dict:
    """Verifies every claim belonging to the document, one at a time,
    then sets status to "done" (or "failed" if the document itself
    doesn't exist, or it has no claims to verify at all -- the latter
    happens when extraction genuinely found nothing checkable, which is
    a real, valid outcome, not an error, but there's nothing for this
    stage to do, so it's recorded distinctly from a normal "done" run
    that verified at least one claim)."""
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is None:
            logger.error("verify_document_claims: no document with id %s", document_id)
            return {"document_id": document_id, "verified": 0, "failed": 0, "error": "document not found"}
        claim_ids = [c.id for c in doc.claims]

    if not claim_ids:
        with get_session() as session:
            doc = session.get(VerificationDocument, document_id)
            doc.status = "done"
        logger.info("Document %s: no claims to verify (extraction found nothing checkable)", document_id)
        return {"document_id": document_id, "verified": 0, "failed": 0}

    verified_count = 0
    failed_count = 0
    for claim_id in claim_ids:
        if run_verification(claim_id):
            verified_count += 1
        else:
            failed_count += 1

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        doc.status = "done"

    logger.info("Document %s: verification finished, %d verified, %d failed",
                document_id, verified_count, failed_count)
    return {"document_id": document_id, "verified": verified_count, "failed": failed_count}