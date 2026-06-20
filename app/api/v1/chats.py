from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.db.session import get_session
from app.models.chat import Chat
from app.api.v1.schemas import ChatSummarySchema, ChatDetailSchema
from app.api.v1.serializers import chat_to_summary_dict, chat_to_detail_dict

blp = Blueprint(
    "chats", __name__,
    url_prefix="/api/v1/chats",
    description="Persisted chat history",
)


@blp.route("/")
class ChatList(MethodView):
    @jwt_required()
    @blp.response(200, ChatSummarySchema(many=True))
    def get(self):
        """List the current user's chat threads, most recent first."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            chats = (
                session.query(Chat)
                .filter_by(user_id=user_id)
                .order_by(Chat.created_at.desc())
                .all()
            )
            return [chat_to_summary_dict(c) for c in chats]


@blp.route("/<int:chat_id>")
class ChatDetail(MethodView):
    @jwt_required()
    @blp.response(200, ChatDetailSchema)
    def get(self, chat_id):
        """Get a chat thread's full message history, including citations."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None or chat.user_id != user_id:
                abort(404, message="Chat not found")
            return chat_to_detail_dict(chat)

    @jwt_required()
    def delete(self, chat_id):
        """Delete a chat thread and everything in it."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None or chat.user_id != user_id:
                abort(404, message="Chat not found")
            session.delete(chat)
        return "", 204
