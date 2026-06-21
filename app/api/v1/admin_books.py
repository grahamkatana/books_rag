"""
Admin-only endpoints for managing book bibliography via the API, as an
alternative to the /admin server-rendered panel. Every endpoint here
requires admin_required (a real DB lookup, not just a JWT claim -- see
app/auth/decorators.py).

Endpoints:
    GET /api/v1/admin/books/        list every book
    GET /api/v1/admin/books/<id>    get one book
    PUT /api/v1/admin/books/<id>    update a book's bibliography

No DELETE here, and that's deliberate, not an oversight: a Book row has
real Qdrant vectors and a data/chunks/<source_key>.jsonl file associated
with it that nothing in this project currently cleans up. Deleting just
the database row would leave those chunks searchable forever with no
Book left to resolve their citation against -- same reasoning the
Flask-Admin panel's BookAdminView now follows too (can_delete = False
there as well, as of this file existing).

A manual edit through here is the same kind of action as editing
through /admin: it's a human having looked at the data, so it gets
marked bibliography_verified=True and bibliography_source="manual"
automatically, exactly like the Flask-Admin path does.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.db.session import get_session
from app.models.book import Book
from app.auth.decorators import admin_required

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