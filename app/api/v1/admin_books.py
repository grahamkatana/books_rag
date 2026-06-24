"""
Admin-only endpoints for managing book bibliography via the API, as an
alternative to the /admin server-rendered panel. Every endpoint here
requires admin_required (a real DB lookup, not just a JWT claim -- see
app/auth/decorators.py).

Endpoints:
    GET    /api/v1/admin/books/        list every book
    GET    /api/v1/admin/books/<id>    get one book
    PUT    /api/v1/admin/books/<id>    update a book's bibliography
    DELETE /api/v1/admin/books/<id>    enqueue full deletion as a background job
    POST   /api/v1/admin/books/upload  upload a new book PDF and enqueue the full ingestion pipeline

A book's vectors, chunk file, and DB row are deleted together by
app/ingestion/delete_book.py -- this endpoint never deletes anything
itself, it only enqueues delete_book_task (app/worker/tasks.py) and
returns 202 with a task_id immediately, since the operation runs
out-of-band on a Celery worker rather than blocking this request for
however long it takes. Poll GET /api/v1/admin/jobs/<task_id> for the
result. DELETE was deliberately withheld here until that worker
infrastructure existed -- offering just the DB-row half of the
operation would have left Qdrant vectors and the chunk file orphaned
forever, which is exactly why this took this long to add.

Upload follows the same shape: the file is saved to pdfs/books/ and
run_books_pipeline_task is enqueued -- the exact same report ->
seed-books -> lookup-bibliography -> chunk -> embed sequence
`uv run python ingest.py` runs, just triggered from here instead of a
terminal. force=False always -- a freshly uploaded file has a
source_key nothing has seen before, so there's nothing for force to
need to override.

A manual edit through here is the same kind of action as editing
through /admin: it's a human having looked at the data, so it gets
marked bibliography_verified=True and bibliography_source="manual"
automatically, exactly like the Flask-Admin path does.
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.config import PDF_DIR
from app.db.session import get_session
from app.models.book import Book
from app.auth.decorators import admin_required
from app.api.v1.schemas import DeleteQuerySchema, JobQueuedSchema
from app.api.v1.upload_common import save_uploaded_pdf

blp = Blueprint(
    "admin_books", __name__,
    url_prefix="/api/v1/admin/books",
    description="Admin-only book bibliography management (list/get/update)",
)


class AdminBookSchema(Schema):
    id = fields.Int()
    source_key = fields.Str()
    title = fields.Str()
    authors = fields.Str(allow_none=True)
    is_editor = fields.Bool()
    year = fields.Int(allow_none=True)
    publisher = fields.Str(allow_none=True)
    edition = fields.Str(allow_none=True)
    page_mode = fields.Str()
    work_key = fields.Str(allow_none=True)
    is_preferred_edition = fields.Bool()
    edition_pinned = fields.Bool()
    bibliography_verified = fields.Bool()
    bibliography_source = fields.Str(allow_none=True)
    lookup_confidence = fields.Str(allow_none=True)


class AdminBookUpdateSchema(Schema):
    # Every field optional -- a partial update, same pattern as
    # AdminUserUpdateSchema. source_key and page_mode are deliberately
    # NOT editable here: source_key is the join key against Qdrant's
    # chunk payloads, and page_mode reflects how the PDF was actually
    # chunked (trusted vs. untrusted) -- neither is "bibliography",
    # they're structural facts about the ingested file.
    title = fields.Str(required=False)
    authors = fields.Str(required=False, allow_none=True)
    is_editor = fields.Bool(required=False)
    year = fields.Int(required=False, allow_none=True)
    publisher = fields.Str(required=False, allow_none=True)
    edition = fields.Str(required=False, allow_none=True)
    work_key = fields.Str(required=False, allow_none=True)
    is_preferred_edition = fields.Bool(required=False)
    edition_pinned = fields.Bool(required=False)


def book_to_dict(book: Book) -> dict:
    return {
        "id": book.id,
        "source_key": book.source_key,
        "title": book.title,
        "authors": book.authors,
        "is_editor": book.is_editor,
        "year": book.year,
        "publisher": book.publisher,
        "edition": book.edition,
        "page_mode": book.page_mode,
        "work_key": book.work_key,
        "is_preferred_edition": book.is_preferred_edition,
        "edition_pinned": book.edition_pinned,
        "bibliography_verified": book.bibliography_verified,
        "bibliography_source": book.bibliography_source,
        "lookup_confidence": book.lookup_confidence,
    }


@blp.route("/")
class AdminBookList(MethodView):
    @admin_required
    @blp.response(200, AdminBookSchema(many=True))
    def get(self):
        """List every book."""
        with get_session() as session:
            books = session.query(Book).order_by(Book.title).all()
            return [book_to_dict(b) for b in books]


@blp.route("/<int:book_id>")
class AdminBookDetail(MethodView):
    @admin_required
    @blp.response(200, AdminBookSchema)
    def get(self, book_id):
        """Get one book by id."""
        with get_session() as session:
            book = session.get(Book, book_id)
            if book is None:
                abort(404, message="Book not found")
            return book_to_dict(book)

    @admin_required
    @blp.arguments(AdminBookUpdateSchema)
    @blp.response(200, AdminBookSchema)
    def put(self, args, book_id):
        """Update a book's bibliography. Any field can be omitted to leave it unchanged."""
        with get_session() as session:
            book = session.get(Book, book_id)
            if book is None:
                abort(404, message="Book not found")

            for field, value in args.items():
                setattr(book, field, value)

            # Same rule as the Flask-Admin panel: a manual edit through
            # the API is, definitionally, a human having looked at it.
            book.bibliography_verified = True
            book.bibliography_source = "manual"

            session.add(book)
            session.flush()
            return book_to_dict(book)

    @admin_required
    @blp.arguments(DeleteQuerySchema, location="query")
    @blp.response(202, JobQueuedSchema)
    def delete(self, query_args, book_id):
        """Enqueue full deletion (Qdrant vectors, chunk file, manifest
        entry, and the DB row) as a background job. Returns immediately
        with a task_id -- this never blocks on the actual deletion, and
        never performs it inline. Poll GET /api/v1/admin/jobs/<task_id>
        to find out when it's actually done."""
        with get_session() as session:
            book = session.get(Book, book_id)
            if book is None:
                abort(404, message="Book not found")
            source_key = book.source_key

        from app.worker.tasks import delete_book_task
        async_result = delete_book_task.delay(source_key, delete_pdf=query_args["delete_pdf"])
        return {"task_id": async_result.id, "source_key": source_key, "status": "queued"}


@blp.route("/upload")
class AdminBookUpload(MethodView):
    @admin_required
    @blp.response(202, JobQueuedSchema)
    def post(self):
        """Uploads a new book PDF to pdfs/books/ and enqueues the full
        ingestion pipeline as a background job. Returns immediately
        with a task_id -- poll GET /api/v1/admin/jobs/<task_id> for the
        result. Send the file as multipart/form-data under the field
        name "file"."""
        destination = save_uploaded_pdf(request.files.get("file"), PDF_DIR)
        source_key = destination.stem

        from app.worker.tasks import run_books_pipeline_task
        async_result = run_books_pipeline_task.delay(force=False)
        return {"task_id": async_result.id, "source_key": source_key, "status": "queued"}