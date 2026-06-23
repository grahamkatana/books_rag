"""
Converts an uploaded .docx into markdown using Docling -- the same
DocumentConverter already used for papers (app/ingestion/chunk_papers.py),
reused here rather than adding a second document-parsing library for
what's fundamentally the same kind of task: turn a real document format
into clean, structure-aware markdown. Requires `docling` to be
installed (see the README's papers-pipeline setup -- same dependency,
no second heavy install needed if you've already got it for papers).

This module owns the FIRST stage of the verification pipeline only:
save the upload, convert it, record the result. Claim extraction and
verification are separate, later stages (their own modules, once
built) -- kept apart here so each stage's failure is independently
visible and retryable in VerificationDocument.status, the same
philosophy as every other multi-step pipeline in this project.
"""

from pathlib import Path

from app.config import VERIFICATION_UPLOADS_DIR
from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.logging_config import get_logger

logger = get_logger(__name__)


def convert_docx_to_markdown(docx_path: Path) -> str:
    """The one function that actually calls Docling. Deliberately thin
    -- conversion only, no markdown post-processing here -- so this can
    be swapped or extended without touching whatever calls it, and so
    importing this module doesn't require docling to be installed at
    all unless this specific function actually runs (lazy import,
    same pattern chunk_papers.py already uses)."""
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(docx_path))
    return result.document.export_to_markdown()


def save_upload(file_bytes: bytes, filename: str, document_id: int) -> Path:
    """Persists the uploaded file under its document's own id rather
    than its original filename, so two uploads named the same thing
    (a very real possibility -- "thesis_draft.docx" is an extremely
    common filename) never collide on disk."""
    VERIFICATION_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix or ".docx"
    saved_path = VERIFICATION_UPLOADS_DIR / f"{document_id}{suffix}"
    saved_path.write_bytes(file_bytes)
    return saved_path


def ingest_verification_document(file_bytes: bytes, filename: str, user_id: int | None = None) -> int:
    """Creates the VerificationDocument row, saves the upload, converts
    it to markdown, and updates the row's status throughout --
    "uploaded" -> "converting" -> "extracting_claims" (ready for the
    next stage) or "failed" (with error_message set, never raising past
    this function -- a bad upload is an expected outcome to record, not
    an exception for the caller to handle).

    Returns the document's id either way, so a caller (the upload API
    endpoint, eventually) always has something to point the user at,
    whether conversion succeeded or not."""
    with get_session() as session:
        doc = VerificationDocument(user_id=user_id, filename=filename, status="uploaded")
        session.add(doc)
        session.flush()
        document_id = doc.id

    try:
        saved_path = save_upload(file_bytes, filename, document_id)
    except Exception as e:
        logger.error("Failed to save upload for document %s (%s): %s", document_id, filename, e)
        _mark_failed(document_id, f"Could not save the uploaded file: {e}")
        return document_id

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        doc.status = "converting"

    try:
        markdown = convert_docx_to_markdown(saved_path)
    except Exception as e:
        logger.error("Failed to convert document %s (%s) to markdown: %s", document_id, filename, e)
        _mark_failed(document_id, f"Conversion to markdown failed: {e}")
        return document_id

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        doc.markdown = markdown
        doc.status = "extracting_claims"

    logger.info("Document %s (%s) converted successfully, %d markdown chars", document_id, filename, len(markdown))
    return document_id


def _mark_failed(document_id: int, error_message: str) -> None:
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error_message = error_message