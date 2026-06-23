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