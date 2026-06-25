"""
Celery tasks wrapping the plain delete_book()/delete_paper() functions,
and the full books/papers ingestion pipelines. No pipeline or deletion
logic lives here at all -- this is intentionally a thin wrapper, the
same DRY principle as everything else in this project's ingestion
layer: the underlying functions (app/ingestion/delete_book.py,
delete_paper.py, and app/cli.py's cmd_pipeline/cmd_pipeline_papers) are
callable identically whether invoked directly (the CLI, a test) or
through a worker, with zero duplicated behavior to drift out of sync.
"""

from types import SimpleNamespace

from app.worker.celery_app import celery_app
from app.logging_config import get_logger

logger = get_logger(__name__)


@celery_app.task(name="delete_book_task", bind=True)
def delete_book_task(self, source_key: str, delete_pdf: bool = False) -> dict:
    from app.ingestion.delete_book import delete_book
    logger.info("delete_book_task starting for %s (task_id=%s)", source_key, self.request.id)
    result = delete_book(source_key, delete_pdf=delete_pdf)
    logger.info("delete_book_task finished for %s: %s", source_key, result)
    return result


@celery_app.task(name="delete_paper_task", bind=True)
def delete_paper_task(self, source_key: str, delete_pdf: bool = False) -> dict:
    from app.ingestion.delete_paper import delete_paper
    logger.info("delete_paper_task starting for %s (task_id=%s)", source_key, self.request.id)
    result = delete_paper(source_key, delete_pdf=delete_pdf)
    logger.info("delete_paper_task finished for %s: %s", source_key, result)
    return result


@celery_app.task(name="run_books_pipeline_task", bind=True)
def run_books_pipeline_task(self, force: bool = False) -> str:
    """Runs report -> seed-books -> lookup-bibliography -> chunk -> embed,
    exactly as `uv run python ingest.py` does -- this calls the very
    same cmd_pipeline() function the CLI command does, just handed a
    plain stand-in for the argparse Namespace it expects (it only ever
    reads .force off it) instead of one actually parsed from argv.
    A real failure partway through propagates as a normal exception --
    Celery's own state tracking (confirmed in test_celery_tasks.py)
    already turns that into a correctly-reported FAILURE state with
    the real error, so there's no need to catch and reshape it here."""
    from app.cli import cmd_pipeline
    logger.info("run_books_pipeline_task starting (task_id=%s, force=%s)", self.request.id, force)
    cmd_pipeline(SimpleNamespace(force=force))
    logger.info("run_books_pipeline_task finished (task_id=%s)", self.request.id)
    return "done"


@celery_app.task(name="run_papers_pipeline_task", bind=True)
def run_papers_pipeline_task(self, force: bool = False) -> str:
    """Runs seed-papers -> lookup-paper-doi -> chunk-papers -> embed-papers,
    exactly as `uv run python ingest_papers.py` does -- same reasoning
    as run_books_pipeline_task above, just calling cmd_pipeline_papers()
    instead."""
    from app.cli import cmd_pipeline_papers
    logger.info("run_papers_pipeline_task starting (task_id=%s, force=%s)", self.request.id, force)
    cmd_pipeline_papers(SimpleNamespace(force=force))
    logger.info("run_papers_pipeline_task finished (task_id=%s)", self.request.id)
    return "done"


@celery_app.task(name="run_verification_pipeline_task", bind=True)
def run_verification_pipeline_task(self, document_id: int, saved_path: str) -> dict:
    """Runs the rest of the document-verification pipeline after the
    upload endpoint has already done the fast, synchronous part
    (creating the VerificationDocument row and saving the file) --
    convert -> extract claims -> verify every claim, in that order.
    Each stage already records its own failure in
    VerificationDocument.status/error_message without raising, so this
    task only needs to stop early if an earlier stage didn't succeed;
    it doesn't need its own try/except to translate failures into
    something else."""
    from pathlib import Path
    from app.ingestion.convert_docx import convert_uploaded_document
    from app.agents.extract_claims import run_claim_extraction
    from app.agents.verify_document import verify_document_claims

    logger.info("run_verification_pipeline_task starting for document %s (task_id=%s)", document_id, self.request.id)

    if not convert_uploaded_document(document_id, Path(saved_path)):
        logger.info("run_verification_pipeline_task stopped at conversion for document %s", document_id)
        return {"document_id": document_id, "stage": "converting", "succeeded": False}

    claim_count = run_claim_extraction(document_id)
    # run_claim_extraction returning 0 is ambiguous on its own (it means
    # either "extraction genuinely found nothing checkable" or
    # "extraction itself failed") -- check the document's own status,
    # which extract_claims.py already set correctly in either case,
    # rather than re-deriving that distinction here from a bare count.
    from app.db.session import get_session
    from app.models.verification import VerificationDocument
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        extraction_failed = doc is not None and doc.status == "failed"

    if extraction_failed:
        logger.info("run_verification_pipeline_task stopped at extraction for document %s", document_id)
        return {"document_id": document_id, "stage": "extracting_claims", "succeeded": False}

    result = verify_document_claims(document_id)
    logger.info("run_verification_pipeline_task finished for document %s: %s", document_id, result)
    return {"document_id": document_id, "stage": "done", "succeeded": True, **result}


@celery_app.task(name="rerun_verification_task", bind=True)
def rerun_verification_task(self, document_id: int, from_extraction: bool = True) -> dict:
    """Re-runs verification (or extraction+verification) for a document
    that's already been through the pipeline once -- see
    app/agents/rerun_verification.py for the full reasoning on the two
    modes. Wrapped as its own task, separate from
    run_verification_pipeline_task, since it doesn't need (and
    shouldn't need) a saved_path argument at all -- the markdown is
    already on the row from the first run."""
    from app.agents.rerun_verification import rerun_verification
    logger.info("rerun_verification_task starting for document %s (task_id=%s, from_extraction=%s)",
                document_id, self.request.id, from_extraction)
    result = rerun_verification(document_id, from_extraction=from_extraction)
    logger.info("rerun_verification_task finished for document %s: %s", document_id, result)
    return result