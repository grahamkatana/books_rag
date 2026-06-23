"""
Celery tasks wrapping the plain delete_book()/delete_paper() functions.
No deletion logic lives here at all -- this is intentionally a thin
wrapper, the same DRY principle as everything else in this project's
ingestion layer: app/ingestion/delete_book.py and delete_paper.py are
callable identically whether invoked directly (the CLI, a test) or
through a worker, with zero duplicated behavior to drift out of sync.
"""

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