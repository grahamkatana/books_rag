"""
Per-user document verification: upload a .docx, get its checkable
claims verified against the existing book/paper corpus (and the web,
where the agent judges the corpus doesn't address a claim). Scoped to
the uploading user exactly like chats.py already is -- this is "verify
MY document," not an admin operation, so it lives outside /admin
entirely and reuses chats.py's own jwt_required() + user_id ownership
check rather than admin_required.

Endpoints:
    POST   /api/v1/verification/                     upload a .docx, enqueue the pipeline
    GET    /api/v1/verification/                      list the current user's verification documents
    GET    /api/v1/verification/<id>                  full detail: claims, verdicts, evidence
    DELETE /api/v1/verification/<id>                  delete a verification document and everything under it
    POST   /api/v1/verification/<id>/rerun             re-extract+re-verify, or just re-verify, an already-verified document
    POST   /api/v1/verification/<id>/cross-check       cross-check existing verdicts using a second model (Claude)

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
This is also why rerun and cross-check are deliberately NOT exposed
through /api/v1/admin/jobs/: that endpoint is admin-only, and neither
of these is an admin action -- a regular user re-running or
cross-checking their own document needs to poll the same document
endpoint they already have ownership-checked access to, not a
different admin-gated one.

rerun's completion is visible exactly the same way the original
pipeline's was: the document's own .status reaches "done" or "failed"
again, so the existing poll-until-done logic on the frontend needs no
changes at all to support it. cross-check is different -- it never
touches .status, since it's reviewing already-verified claims, not
running the pipeline -- so this endpoint returns the specific claim_ids
it will touch, letting the caller poll for cross_check appearing on
exactly those claims instead.

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
from app.agents.cross_check_claim import REVIEWABLE_VERDICTS
from app.api.v1.schemas import (
    VerificationDocumentSummarySchema, VerificationDocumentDetailSchema, JobQueuedSchema,
    RerunQuerySchema, CrossCheckQuerySchema, CrossCheckQueuedSchema,
)
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


@blp.route("/<int:document_id>/rerun")
class VerificationRerun(MethodView):
    @jwt_required()
    @blp.arguments(RerunQuerySchema, location="query")
    @blp.response(202, JobQueuedSchema)
    def post(self, query_args, document_id):
        """Re-runs verification for a document that's already been
        through the pipeline once -- see
        app/agents/rerun_verification.py for the full reasoning on the
        two modes. Returns immediately with a task_id; poll
        GET /api/v1/verification/<id> the same way the original
        upload's pipeline is polled -- the document's own .status
        reaches "done" or "failed" again exactly the same way, no new
        polling logic needed on the client."""
        user_id = int(get_jwt_identity())
        with get_session() as session:
            doc = session.get(VerificationDocument, document_id)
            if doc is None or doc.user_id != user_id:
                abort(404, message="Verification document not found")
            if not doc.markdown:
                abort(400, message="This document has no stored markdown to rerun against -- it may have failed before conversion completed.")

        from app.worker.tasks import rerun_verification_task
        async_result = rerun_verification_task.delay(document_id, from_extraction=query_args["from_extraction"])
        return {"task_id": async_result.id, "source_key": str(document_id), "status": "queued"}


@blp.route("/<int:document_id>/cross-check")
class VerificationCrossCheck(MethodView):
    @jwt_required()
    @blp.arguments(CrossCheckQuerySchema, location="query")
    @blp.response(202, CrossCheckQueuedSchema)
    def post(self, query_args, document_id):
        """Enqueues a cross-check pass (a second, independent model
        opinion -- see app/agents/cross_check_claim.py) over this
        document's already-verified claims. Returns immediately with
        the task_id AND the specific claim_ids this pass will actually
        touch, since cross-checking never changes the document's own
        .status (it's reviewing existing verdicts, not running the
        pipeline) -- poll GET /api/v1/verification/<id> and watch for
        cross_check appearing on exactly those claim_ids."""
        user_id = int(get_jwt_identity())
        target_verdicts = query_args.get("verdicts") or REVIEWABLE_VERDICTS
        with get_session() as session:
            doc = session.get(VerificationDocument, document_id)
            if doc is None or doc.user_id != user_id:
                abort(404, message="Verification document not found")
            claim_ids = [
                c.id for c in doc.claims
                if c.verification is not None and c.verification.verdict in target_verdicts
            ]

        from app.worker.tasks import cross_check_document_task
        async_result = cross_check_document_task.delay(document_id, verdicts_to_check=query_args.get("verdicts"))
        return {"task_id": async_result.id, "document_id": document_id, "claim_ids": claim_ids, "status": "queued"}