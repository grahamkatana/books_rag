"""
Admin-only endpoints for chat moderation -- list/view/delete ANY user's
chat, unlike /api/v1/chats/* which is scoped to whichever user the JWT
belongs to. Every endpoint here requires admin_required (a real DB
lookup, not just a JWT claim -- see app/auth/decorators.py).

Endpoints:
    GET    /api/v1/admin/chats/        list every chat, across all users
    GET    /api/v1/admin/chats/<id>    full message history for any chat
    DELETE /api/v1/admin/chats/<id>    delete any chat and its messages

No update endpoint -- there's nothing meaningful to "edit" on a chat;
moderation here means viewing and removing, not rewriting someone's
conversation history.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from marshmallow import Schema, fields

from app.db.session import get_session
from app.models.chat import Chat
from app.models.user import User
from app.auth.decorators import admin_required

blp = Blueprint(
    "admin_chats", __name__,
    url_prefix="/api/v1/admin/chats",
    description="Admin-only chat moderation (list/view/delete across all users)",
)


class AdminChatSummarySchema(Schema):
    id = fields.Int()
    title = fields.Str(allow_none=True)
    created_at = fields.DateTime()
    message_count = fields.Int()
    user_id = fields.Int(allow_none=True)
    user_email = fields.Str(allow_none=True)


class AdminMessageSchema(Schema):
    id = fields.Int()
    role = fields.Str()
    content = fields.Str()
    created_at = fields.DateTime()


class AdminChatDetailSchema(Schema):
    id = fields.Int()
    title = fields.Str(allow_none=True)
    created_at = fields.DateTime()
    user_id = fields.Int(allow_none=True)
    user_email = fields.Str(allow_none=True)
    messages = fields.List(fields.Nested(AdminMessageSchema))


def chat_to_admin_summary_dict(chat: Chat, email_by_user_id: dict) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "message_count": len(chat.messages),
        "user_id": chat.user_id,
        "user_email": email_by_user_id.get(chat.user_id),  # None for CLI-created, ownerless chats
    }


def chat_to_admin_detail_dict(chat: Chat, user_email: str | None) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "user_id": chat.user_id,
        "user_email": user_email,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in chat.messages
        ],
    }


@blp.route("/")
class AdminChatList(MethodView):
    @admin_required
    @blp.response(200, AdminChatSummarySchema(many=True))
    def get(self):
        """List every chat across every user, most recent first."""
        with get_session() as session:
            chats = session.query(Chat).order_by(Chat.created_at.desc()).all()
            # One query for every user's email up front, rather than a
            # query-per-chat -- this list can have a lot of rows.
            email_by_user_id = {u.id: u.email for u in session.query(User).all()}
            return [chat_to_admin_summary_dict(c, email_by_user_id) for c in chats]


@blp.route("/<int:chat_id>")
class AdminChatDetail(MethodView):
    @admin_required
    @blp.response(200, AdminChatDetailSchema)
    def get(self, chat_id):
        """Full message history for any chat, regardless of owner."""
        with get_session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                abort(404, message="Chat not found")
            user = session.get(User, chat.user_id) if chat.user_id else None
            return chat_to_admin_detail_dict(chat, user.email if user else None)

    @admin_required
    def delete(self, chat_id):
        """Delete any chat and its messages, regardless of owner."""
        with get_session() as session:
            chat = session.get(Chat, chat_id)
            if chat is None:
                abort(404, message="Chat not found")
            session.delete(chat)
        return "", 204