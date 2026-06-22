from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required

from app.db.session import get_session
from app.models.paper import Paper
from app.api.v1.schemas import PaperSchema
from app.api.v1.serializers import paper_to_dict

blp = Blueprint(
    "papers", __name__,
    url_prefix="/api/v1/papers",
    description="Bibliographic metadata for papers in the library",
)


@blp.route("/")
class PaperList(MethodView):
    @jwt_required()
    @blp.response(200, PaperSchema(many=True))
    def get(self):
        """List every paper known to the library, with its bibliographic data."""
        with get_session() as session:
            papers = session.query(Paper).order_by(Paper.title).all()
            return [paper_to_dict(p) for p in papers]


@blp.route("/<int:paper_id>")
class PaperDetail(MethodView):
    @jwt_required()
    @blp.response(200, PaperSchema)
    def get(self, paper_id):
        """Get one paper's bibliographic data by its database id."""
        with get_session() as session:
            paper = session.get(Paper, paper_id)
            if paper is None:
                abort(404, message="Paper not found")
            return paper_to_dict(paper)