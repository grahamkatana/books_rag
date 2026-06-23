"""
Celery application instance.

Run a worker with:
    uv run celery -A app.worker.celery_app worker --loglevel=info

(On Windows, Celery's default "prefork" worker pool doesn't work --
add --pool=solo for local development there:
    uv run celery -A app.worker.celery_app worker --loglevel=info --pool=solo
)
"""

from celery import Celery

from app.config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from app.logging_config import setup_logging

setup_logging()

celery_app = Celery(
    "book_rag",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Without this, a client polling a task's status only ever sees
    # PENDING right up until SUCCESS/FAILURE -- there's no visibility
    # into "a worker has actually picked this up and is running it"
    # versus "still sitting in the queue." Cheap to enable, genuinely
    # useful for the polling status endpoint built on top of this.
    task_track_started=True,
)