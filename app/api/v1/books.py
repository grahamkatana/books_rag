from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required

from app.db.session import get_session
from app.models.book import Book
from app.api.v1.schemas import BookSchema
from app.api.v1.serializers import book_to_dict

blp = Blueprint(
    "books", __name__,
    url_prefix="/api/v1/books",
    description="Bibliographic metadata for books in the library",
)


@blp.route("/")
class BookList(MethodView):
    @jwt_required()
    @blp.response(200, BookSchema(many=True))
    def get(self):
        """List every book known to the library, with its bibliographic data."""
        with get_session() as session:
            books = session.query(Book).order_by(Book.title).all()
            return [book_to_dict(b) for b in books]


@blp.route("/<int:book_id>")
class BookDetail(MethodView):
    @jwt_required()
    @blp.response(200, BookSchema)
    def get(self, book_id):
        """Get one book's bibliographic data by its database id."""
        with get_session() as session:
            book = session.get(Book, book_id)
            if book is None:
                abort(404, message="Book not found")
            return book_to_dict(book)
