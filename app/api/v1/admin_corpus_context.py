"""
Admin-only: review corpus_context_checks (see
scripts/check_corpus_context.py) and toggle marked_for_delete. This
endpoint deliberately never deletes a book or paper itself -- actual
deletion goes through the existing, already-tested
/api/v1/admin/books/<id> and /api/v1/admin/papers/<id> DELETE
endpoints, dispatched by the frontend based on each flagged item's own
item_type. Deleting a book or paper already has one correct code path
(Qdrant vector cleanup, chunk file removal, the DB row); this feature
should never grow a second one just because the trigger to delete
came from a different page.

A check whose underlying book/paper has since been deleted (its
book_id/paper_id went SET NULL, per the FK on CorpusContextCheck) is
filtered out of the list automatically -- a stale check with nothing
left to act on isn't worth showing, and there's no separate cleanup
step needed for it: it simply stops appearing.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.auth.decorators import admin_required
from app.db.session import get_session
from app.models.corpus_context_check import CorpusContextCheck

blp = Blueprint(
    "admin_corpus_context", __name__,
    url_prefix="/api/v1/admin/corpus-context-checks",
    description="Admin-only: review corpus context checks and flagged-for-deletion candidates",
)


class CorpusContextCheckSchema(Schema):
    id = fields.Int()
    item_type = fields.Str()  # "book" or "paper", resolved server-side from which FK is set
    item_id = fields.Int()    # the actual book.id or paper.id, for the frontend to call the right delete endpoint
    source_key = fields.Str()
    title = fields.Str()
    context_known = fields.Bool()
    explanation = fields.Str(allow_none=True)
    marked_for_delete = fields.Bool()
    checked_at = fields.DateTime()


class CorpusContextCheckUpdateSchema(Schema):
    marked_for_delete = fields.Bool(required=True)


def check_to_dict(check: CorpusContextCheck) -> dict | None:
    """Returns None if the underlying book/paper is already gone --
    see the module docstring for why that's the right thing to do
    here, not an error."""
    if check.book_id is not None and check.book is not None:
        item_type, item_id, source_key, title = "book", check.book_id, check.book.source_key, check.book.title
    elif check.paper_id is not None and check.paper is not None:
        item_type, item_id, source_key, title = "paper", check.paper_id, check.paper.source_key, check.paper.title
    else:
        return None

    return {
        "id": check.id,
        "item_type": item_type,
        "item_id": item_id,
        "source_key": source_key,
        "title": title,
        "context_known": check.context_known,
        "explanation": check.explanation,
        "marked_for_delete": check.marked_for_delete,
        "checked_at": check.checked_at,
    }


@blp.route("/")
class CorpusContextCheckList(MethodView):
    @admin_required
    @blp.response(200, CorpusContextCheckSchema(many=True))
    def get(self):
        """Lists every corpus context check, most recently checked
        first. Includes context_known=True rows too, not just flagged
        ones -- an admin reviewing this should see the full picture
        the last check run produced, not just the candidates it
        already proposed for deletion."""
        with get_session() as session:
            checks = session.query(CorpusContextCheck).order_by(CorpusContextCheck.checked_at.desc()).all()
            return [d for d in (check_to_dict(c) for c in checks) if d is not None]


@blp.route("/<int:check_id>")
class CorpusContextCheckDetail(MethodView):
    @admin_required
    @blp.arguments(CorpusContextCheckUpdateSchema)
    @blp.response(200, CorpusContextCheckSchema)
    def put(self, update_data, check_id):
        """Toggles marked_for_delete -- the only field on a check an
        admin should ever edit directly. context_known and explanation
        only ever come from re-running the script; overwriting them by
        hand would make the next script run's diff meaningless."""
        with get_session() as session:
            check = session.get(CorpusContextCheck, check_id)
            if check is None:
                abort(404, message="Corpus context check not found")
            check.marked_for_delete = update_data["marked_for_delete"]
            session.flush()
            result = check_to_dict(check)
        if result is None:
            abort(404, message="The underlying book/paper for this check no longer exists")
        return result