"""
Per-user document verification: upload a .docx, get its checkable
claims verified against the existing book/paper corpus (and the web,
where the agent judges the corpus doesn't address a claim). Scoped to
the uploading user exactly like chats.py already is -- this is "verify
MY document," not an admin operation, so it lives outside /admin
entirely and reuses chats.py's own jwt_required() + user_id ownership
check rather than admin_required.

Endpoints:
    POST   /api/v1/verification/          upload a .docx, enqueue the pipeline
    GET    /api/v1/verification/          list the current user's verification documents
    GET    /api/v1/verification/<id>      full detail: claims, verdicts, evidence
    DELETE /api/v1/verification/<id>      delete a verification document and everything under it

The upload endpoint only does the fast, synchronous part (save the
file, create the row) and hands the rest -- convert, extract claims,
verify each one -- to run_verification_pipeline_task as a single
background job, the same shape as the books/papers upload endpoints.

Poll GET /api/v1/verification/<id> directly for status and results,
not the generic /api/v1/admin/jobs/<task_id> endpoint: that endpoint
fits an action whose result is a single summary dict (deleting a book,
running a pipeline). Here, the actual result *is* the document's own
claims and verdicts, which already need their own endpoint to fetch --
there's no value returning the same data twice through two routes.

No filename-collision handling needed here, unlike the book/paper
uploads: save_upload() (convert_docx.py) keys files by the document's
own database id, not its filename, so two uploads of
"thesis_draft.docx" from two different users (or the same user twice)
simply can't collide on disk.
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.api.v1.schemas import VerificationDocumentSummarySchema, VerificationDocumentDetailSchema, JobQueuedSchema
from app.api.v1.serializers import verification_document_to_summary_dict, verification_document_to_detail_dict

blp = Blueprint(
    "verification", __name__,
    url_prefix="/api/v1/verification",
    description="Per-user document claim verification",
)


@blp.route("/")
class VerificationList(MethodView):
    @jwt_required()
    @blp.response(200, VerificationDocumentSummarySchema(many=True))
    def get(self):
        """List the current user's verification documents, most recent first."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            docs = (
                session.query(VerificationDocument)
                .filter_by(user_id=user_id)
                .order_by(VerificationDocument.created_at.desc())
                .all()
            )
            return [verification_document_to_summary_dict(d) for d in docs]

    @jwt_required()
    @blp.response(202, JobQueuedSchema)
    def post(self):
        """Uploads a .docx and enqueues the full verification pipeline
        (convert -> extract claims -> verify each one) as a background
        job. Returns immediately with a task_id, but poll
        GET /api/v1/verification/<id> for the actual result -- see the
        module docstring for why that endpoint, not the generic job
        one, is the right one to poll here."""
        user_id = int(get_jwt_identity())
        file = request.files.get("file")
        if not file or not file.filename:
            abort(400, message="No file provided. Send it as multipart/form-data under the 'file' field.")
        if not file.filename.lower().endswith(".docx"):
            abort(400, message="Only .docx files are accepted.")

        from app.ingestion.convert_docx import create_verification_document, save_upload
        document_id = create_verification_document(file.filename, user_id=user_id)
        saved_path = save_upload(file.read(), file.filename, document_id)

        from app.worker.tasks import run_verification_pipeline_task
        async_result = run_verification_pipeline_task.delay(document_id, str(saved_path))
        return {"task_id": async_result.id, "source_key": str(document_id), "status": "queued"}


@blp.route("/<int:document_id>")
class VerificationDetail(MethodView):
    @jwt_required()
    @blp.response(200, VerificationDocumentDetailSchema)
    def get(self, document_id):
        """Get a verification document's full detail: status, and
        every extracted claim with its verdict and evidence, once
        available. A claim with verification=null hasn't been verified
        yet -- that's the natural "X of Y done" progress signal, no
        separate counter needed."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            doc = session.get(VerificationDocument, document_id)
            if doc is None or doc.user_id != user_id:
                abort(404, message="Verification document not found")
            return verification_document_to_detail_dict(doc)

    @jwt_required()
    def delete(self, document_id):
        """Delete a verification document and everything under it
        (claims, verifications, evidence cascade automatically, same
        as a chat deleting its messages)."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            doc = session.get(VerificationDocument, document_id)
            if doc is None or doc.user_id != user_id:
                abort(404, message="Verification document not found")
            session.delete(doc)
        return "", 204