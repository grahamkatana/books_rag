"""
Admin-only endpoints for managing paper bibliography via the API.
Mirrors admin_books.py exactly, including the missing-on-purpose DELETE:
a Paper row has real Qdrant vectors and a
data/papers/chunks/<source_key>.jsonl file associated with it that
nothing in this project currently cleans up. Same reasoning, same gap,
same decision not to offer half of that operation.

Endpoints:
    GET /api/v1/admin/papers/        list every paper
    GET /api/v1/admin/papers/<id>    get one paper
    PUT /api/v1/admin/papers/<id>    update a paper's bibliography
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.db.session import get_session
from app.models.paper import Paper
from app.auth.decorators import admin_required

blp = Blueprint(
    "admin_papers", __name__,
    url_prefix="/api/v1/admin/papers",
    description="Admin-only paper bibliography management (list/get/update)",
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