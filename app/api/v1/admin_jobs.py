"""
Polling endpoint for the status of a background job (currently: a book
or paper deletion, see admin_books.py/admin_papers.py's DELETE methods).

A plain GET-and-poll endpoint on purpose, not a WebSocket or SSE stream
-- a single delete job finishes in well under a second (one Qdrant
filter-delete, two file removals, one DB row), so there's no real
progress to stream, just a pending-or-done transition. If batch deletes
ever become a real feature with genuine incremental progress worth
showing, the right next step is SSE (this project already has a working
pattern for that in /api/v1/ask/stream), not a second, heavier transport
mechanism for the same one-directional shape of problem.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.auth.decorators import admin_required
from app.worker.celery_app import celery_app

blp = Blueprint(
    "admin_jobs", __name__,
    url_prefix="/api/v1/admin/jobs",
    description="Admin-only polling for background job status (book/paper deletion)",
)


class JobStatusSchema(Schema):
    task_id = fields.Str()
    state = fields.Str()  # PENDING | STARTED | SUCCESS | FAILURE (Celery's own states)
    result = fields.Dict(allow_none=True)   # the delete_book/delete_paper summary dict, once SUCCESS
    error = fields.Str(allow_none=True)     # the exception message, if FAILURE


@blp.route("/<string:task_id>")
class JobStatus(MethodView):
    @admin_required
    @blp.response(200, JobStatusSchema)
    def get(self, task_id):
        """Look up a job's current status by its task_id (returned by
        the DELETE endpoints that enqueued it). A task_id that was never
        actually issued by this app looks identical to one that's simply
        still pending -- Celery's result backend has no way to tell
        those apart, since it only stores state for tasks that have
        reached at least STARTED, and treats anything else as PENDING."""
        async_result = celery_app.AsyncResult(task_id)

        response = {"task_id": task_id, "state": async_result.state, "result": None, "error": None}

        if async_result.state == "SUCCESS":
            response["result"] = async_result.result
        elif async_result.state == "FAILURE":
            response["error"] = str(async_result.result)

        return response