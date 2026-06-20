import json

from flask import Response
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.api.clients import get_openai_client, get_qdrant_client
from app.db.session import get_session
from app.retrieval.query_engine import answer_question, answer_question_stream
from app.api.v1.schemas import AskRequestSchema, AskResponseSchema

blp = Blueprint(
    "ask", __name__,
    url_prefix="/api/v1/ask",
    description="Ask a question against the book library",
)


@blp.route("/")
class Ask(MethodView):
    @jwt_required()
    @blp.arguments(AskRequestSchema)
    @blp.response(200, AskResponseSchema)
    def post(self, args):
        """Ask a question and get back the full answer in one response."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            try:
                return answer_question(
                    session, get_openai_client(), get_qdrant_client(),
                    question=args["question"],
                    chat_id=args.get("chat_id"),
                    source_filter=args.get("sources"),
                    top_k=args["top_k"],
                    model=args["model"],
                    all_editions=args["all_editions"],
                    user_id=user_id,
                )
            except PermissionError:
                abort(404, message="Chat not found")


@blp.route("/stream", methods=["POST"])
@jwt_required()
@blp.arguments(AskRequestSchema)
@blp.doc(
    description=(
        "Same as POST /api/v1/ask, but streamed as Server-Sent Events instead "
        "of a single JSON response. Not represented as a typed JSON schema "
        "here since SSE doesn't fit OpenAPI's response model cleanly -- the "
        "wire format is: a 'chat_id' event first, then one 'delta' event per "
        "chunk of answer text as it's generated, then a final 'done' event "
        "carrying the structured citations once the full answer is persisted."
    )
)
def ask_stream(args):
    """Streamed version of asking a question, via Server-Sent Events."""
    openai_client = get_openai_client()
    qdrant_client = get_qdrant_client()

    # Extracted here, NOT inside generate() below: the generator is
    # consumed after this view function returns, by which point Flask's
    # request context (which get_jwt_identity() depends on) may already
    # be gone. Capturing it now and closing over the plain value avoids
    # that entirely.
    user_id = int(get_jwt_identity())

    def generate():
        with get_session() as session:
            try:
                for event_type, payload in answer_question_stream(
                    session, openai_client, qdrant_client,
                    question=args["question"],
                    chat_id=args.get("chat_id"),
                    source_filter=args.get("sources"),
                    top_k=args["top_k"],
                    model=args["model"],
                    all_editions=args["all_editions"],
                    user_id=user_id,
                ):
                    data = {"text": payload} if event_type == "delta" else (
                        {"chat_id": payload} if event_type == "chat_id" else payload
                    )
                    yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
            except PermissionError:
                # The HTTP status is already committed to 200 by this point
                # (streaming has started) -- an "error" SSE event is the
                # only way left to signal this to the client.
                yield f"event: error\ndata: {json.dumps({'message': 'Chat not found'})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
