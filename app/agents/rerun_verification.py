"""
Re-runs the verification pipeline for a document that's already gone
through it once -- the actual point of this is testing a prompt or
logic change against a document you already have results for, without
needing to re-upload the original file at all: the markdown is already
sitting on the VerificationDocument row from the first run, and that's
all extraction needs.

Two distinct modes, because they answer two different questions:

from_extraction=True (the default) -- deletes every existing claim
(cascading to its verification and evidence) and re-extracts from
scratch before re-verifying. Use this after a change to the
EXTRACTION prompt or logic specifically: the existing claims were
produced under the old rules and may not reflect what extraction would
even choose to extract now (this is exactly the case after tightening
EXTRACTION_SYSTEM_PROMPT to stop pulling in bare timeline labels and
the document's own self-referential aims/methodology statements --
the old claim set still has those, a fresh extraction shouldn't).

from_extraction=False -- keeps the existing claims exactly as they
are, deletes only their verifications (so each one goes back to
"pending"), and re-runs verification only. Use this after a change to
the VERIFICATION prompt or logic, or just to retry whichever claims
errored out the first time -- it's meaningfully cheaper since it skips
re-extracting, which is the slower of the two stages on a large
document.
"""

from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.agents.extract_claims import run_claim_extraction
from app.agents.verify_document import verify_document_claims
from app.logging_config import get_logger

logger = get_logger(__name__)


def rerun_verification(document_id: int, from_extraction: bool = True) -> dict:
    """Returns a result dict -- either {"document_id", "error"} if it
    couldn't even start, or {"document_id", "verified", "failed"} (the
    same shape verify_document_claims already returns) once it's done."""
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is None:
            logger.error("rerun_verification: no document with id %s", document_id)
            return {"document_id": document_id, "error": "document not found"}

        if not doc.markdown:
            logger.error("rerun_verification: document %s has no stored markdown to rerun against", document_id)
            return {"document_id": document_id, "error": "no markdown stored for this document -- cannot rerun without re-uploading"}

        if from_extraction:
            # Deleting the claim cascades to its verification, which
            # cascades to its evidence -- the same cascade relationships
            # already established on the model, not anything special
            # to this function.
            for claim in list(doc.claims):
                session.delete(claim)
            doc.status = "extracting_claims"
        else:
            for claim in doc.claims:
                if claim.verification is not None:
                    session.delete(claim.verification)
            doc.status = "verifying"

        doc.error_message = None

    if from_extraction:
        logger.info("rerun_verification: re-extracting claims for document %s", document_id)
        run_claim_extraction(document_id)

    logger.info("rerun_verification: re-verifying claims for document %s", document_id)
    result = verify_document_claims(document_id)
    return {"document_id": document_id, **result}