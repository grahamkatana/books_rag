"""
One endpoint that enqueues BOTH the books and papers ingestion
pipelines at once -- powers the sidebar's "Ingest" button, which
doesn't care which corpus a recent upload landed in, it just means "go
run whatever's new in both folders." Each pipeline runs as its own
separate Celery task (two distinct task_ids come back), since they're
entirely independent operations -- a books pipeline failure has no
bearing on whether the papers pipeline succeeds, and vice versa, so
there's no reason to couple them into one job that fails as a unit.
"""

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import Schema, fields

from app.auth.decorators import admin_required

blp = Blueprint(
    "admin_ingest", __name__,
    url_prefix="/api/v1/admin/ingest",
    description="Admin-only: trigger the full books+papers ingestion pipelines together",
)


class IngestQuerySchema(Schema):
    force = fields.Bool(load_default=False, metadata={
        "description": "Reprocess every step for both pipelines, not just new/changed files"
    })


class IngestQueuedSchema(Schema):
    books_task_id = fields.Str()
    papers_task_id = fields.Str()
    status = fields.Str()


@blp.route("/")
class AdminIngest(MethodView):
    @admin_required
    @blp.arguments(IngestQuerySchema, location="query")
    @blp.response(202, IngestQueuedSchema)
    def post(self, query_args):
        """Enqueues both the books and papers ingestion pipelines as
        two separate background jobs -- the exact same
        report -> seed-books -> lookup-bibliography -> chunk -> embed
        and seed-papers -> lookup-paper-doi -> chunk-papers -> embed-papers
        sequences ingest.py/ingest_papers.py already run. Returns
        immediately with both task_ids; poll
        GET /api/v1/admin/jobs/<task_id> for each."""
        from app.worker.tasks import run_books_pipeline_task, run_papers_pipeline_task
        force = query_args["force"]
        books_result = run_books_pipeline_task.delay(force=force)
        papers_result = run_papers_pipeline_task.delay(force=force)
        return {
            "books_task_id": books_result.id,
            "papers_task_id": papers_result.id,
            "status": "queued",
        }