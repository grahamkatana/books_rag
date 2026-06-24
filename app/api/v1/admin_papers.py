"""
Admin-only endpoints for managing paper bibliography via the API.
Mirrors admin_books.py exactly, including how DELETE and upload work:
DELETE never deletes anything itself, it enqueues delete_paper_task
(app/worker/tasks.py) and returns 202 with a task_id immediately.
Upload saves the file to pdfs/papers/ and enqueues
run_papers_pipeline_task -- the exact same seed-papers ->
lookup-paper-doi -> chunk-papers -> embed-papers sequence
`uv run python ingest_papers.py` runs. Poll GET
/api/v1/admin/jobs/<task_id> for either one's result.

Endpoints:
    GET    /api/v1/admin/papers/        list every paper
    GET    /api/v1/admin/papers/<id>    get one paper
    PUT    /api/v1/admin/papers/<id>    update a paper's bibliography
    DELETE /api/v1/admin/papers/<id>    enqueue full deletion as a background job
    POST   /api/v1/admin/papers/upload  upload a new paper PDF and enqueue the full ingestion pipeline
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.config import PAPER_PDF_DIR
from app.db.session import get_session
from app.models.paper import Paper
from app.auth.decorators import admin_required
from app.api.v1.schemas import DeleteQuerySchema, JobQueuedSchema
from app.api.v1.upload_common import save_uploaded_pdf

blp = Blueprint(
    "admin_papers", __name__,
    url_prefix="/api/v1/admin/papers",
    description="Admin-only paper bibliography management (list/get/update/delete/upload)",
)


class AdminPaperSchema(Schema):
    id = fields.Int()
    source_key = fields.Str()
    title = fields.Str()
    authors = fields.Str(allow_none=True)
    year = fields.Int(allow_none=True)
    venue = fields.Str(allow_none=True)
    doi = fields.Str(allow_none=True)
    abstract = fields.Str(allow_none=True)
    bibliography_verified = fields.Bool()
    bibliography_source = fields.Str(allow_none=True)


class AdminPaperUpdateSchema(Schema):
    # Every field optional -- a partial update, same pattern as
    # AdminBookUpdateSchema. source_key is deliberately NOT editable
    # here, for the same reason it isn't for books: it's the join key
    # against Qdrant's chunk payloads, a structural fact about the
    # ingested file, not bibliography.
    title = fields.Str(required=False)
    authors = fields.Str(required=False, allow_none=True)
    year = fields.Int(required=False, allow_none=True)
    venue = fields.Str(required=False, allow_none=True)
    doi = fields.Str(required=False, allow_none=True)
    abstract = fields.Str(required=False, allow_none=True)


def paper_to_dict(paper: Paper) -> dict:
    return {
        "id": paper.id,
        "source_key": paper.source_key,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "venue": paper.venue,
        "doi": paper.doi,
        "abstract": paper.abstract,
        "bibliography_verified": paper.bibliography_verified,
        "bibliography_source": paper.bibliography_source,
    }


@blp.route("/")
class AdminPaperList(MethodView):
    @admin_required
    @blp.response(200, AdminPaperSchema(many=True))
    def get(self):
        """List every paper."""
        with get_session() as session:
            papers = session.query(Paper).order_by(Paper.title).all()
            return [paper_to_dict(p) for p in papers]


@blp.route("/<int:paper_id>")
class AdminPaperDetail(MethodView):
    @admin_required
    @blp.response(200, AdminPaperSchema)
    def get(self, paper_id):
        """Get one paper by id."""
        with get_session() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                abort(404, message="Paper not found")
            return paper_to_dict(paper)

    @admin_required
    @blp.arguments(AdminPaperUpdateSchema)
    @blp.response(200, AdminPaperSchema)
    def put(self, args, paper_id):
        """Update a paper's bibliography. Any field can be omitted to leave it unchanged."""
        with get_session() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                abort(404, message="Paper not found")

            for field, value in args.items():
                setattr(paper, field, value)

            # Same rule as books: a manual edit through the API is,
            # definitionally, a human having looked at it.
            paper.bibliography_verified = True
            paper.bibliography_source = "manual"

            session.add(paper)
            session.flush()
            return paper_to_dict(paper)

    @admin_required
    @blp.arguments(DeleteQuerySchema, location="query")
    @blp.response(202, JobQueuedSchema)
    def delete(self, query_args, paper_id):
        """Enqueue full deletion (Qdrant vectors, chunk file, manifest
        entry, and the DB row) as a background job. Returns immediately
        with a task_id -- poll GET /api/v1/admin/jobs/<task_id> for the
        result."""
        with get_session() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                abort(404, message="Paper not found")
            source_key = paper.source_key

        from app.worker.tasks import delete_paper_task
        async_result = delete_paper_task.delay(source_key, delete_pdf=query_args["delete_pdf"])
        return {"task_id": async_result.id, "source_key": source_key, "status": "queued"}


@blp.route("/upload")
class AdminPaperUpload(MethodView):
    @admin_required
    @blp.response(202, JobQueuedSchema)
    def post(self):
        """Uploads a new paper PDF to pdfs/papers/ and enqueues the
        full ingestion pipeline as a background job. Returns
        immediately with a task_id -- poll GET
        /api/v1/admin/jobs/<task_id> for the result. Send the file as
        multipart/form-data under the field name "file"."""
        destination = save_uploaded_pdf(request.files.get("file"), PAPER_PDF_DIR)
        source_key = destination.stem

        from app.worker.tasks import run_papers_pipeline_task
        async_result = run_papers_pipeline_task.delay(force=False)
        return {"task_id": async_result.id, "source_key": source_key, "status": "queued"}