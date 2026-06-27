import sys
sys.path.insert(0, ".")

import os
os.environ.setdefault("GOOGLE_API_KEY", "dummy-test-key")
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from unittest.mock import patch

from pydantic_ai.models.test import TestModel

from app.db.session import get_session
from app.models.verification import VerificationDocument
import app.agents.document_context as dc

print("--- google: prefix is clean, no deprecation warning ---")
import warnings
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    agent = dc.build_context_agent()
    assert not caught, f"unexpected warnings: {[str(w.message) for w in caught]}"
print("OK")

print("\n--- format_context_for_prompts ---")
ctx = dc.DocumentContext(
    document_type="Master's thesis research proposal",
    subject_summary="Examines AI adoption risks.",
    self_description="This study aims to produce an empirical account of AI adoption risks.",
    notable_structural_elements=["Appendix B contains a research timeline with bare date labels"],
)
formatted = dc.format_context_for_prompts(ctx)
assert "Master's thesis research proposal" in formatted
assert "NOT externally checkable claims" in formatted
assert "Appendix B contains a research timeline" in formatted

ctx_minimal = dc.DocumentContext(document_type="Published paper", subject_summary="Reports a completed study.")
formatted_minimal = dc.format_context_for_prompts(ctx_minimal)
assert "NOT externally checkable" not in formatted_minimal
assert "Notable structure" not in formatted_minimal
print("OK")

print("\n--- agent plumbing via TestModel ---")
fake_context = dc.DocumentContext(document_type="Thesis", subject_summary="About X.", self_description="Aims to study X.")
with agent.override(model=TestModel(custom_output_args=fake_context.model_dump())):
    context = dc.get_document_context("Some document text.", agent=agent)
assert context.document_type == "Thesis"
print("OK")

original_get_context = dc.get_document_context
try:
    print("\n--- run_document_context: success path ---")
    with get_session() as session:
        doc = VerificationDocument(filename="test_context_doc.docx", status="extracting_claims", markdown="Some real markdown content.")
        session.add(doc)
        session.flush()
        doc_id = doc.id

    dc.get_document_context = lambda markdown, agent=None: fake_context
    assert dc.run_document_context(doc_id) is True
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        assert "Thesis" in doc.document_context
        assert doc.status == "extracting_claims", "context gathering must never change the document's own status"
    print("OK")

    print("\n--- run_document_context: no markdown yet, never calls Gemini ---")
    gemini_called = {"value": False}

    def track_call(markdown, agent=None):
        gemini_called["value"] = True
        return fake_context

    dc.get_document_context = track_call
    with get_session() as session:
        doc2 = VerificationDocument(filename="test_no_markdown.docx", status="converting", markdown=None)
        session.add(doc2)
        session.flush()
        doc2_id = doc2.id
    assert dc.run_document_context(doc2_id) is False
    assert gemini_called["value"] is False
    print("OK")

    print("\n--- run_document_context: Gemini fails -- returns False, document status untouched ---")
    def raise_err(markdown, agent=None):
        raise RuntimeError("simulated Gemini failure")
    dc.get_document_context = raise_err
    with get_session() as session:
        doc3 = VerificationDocument(filename="test_gemini_fails.docx", status="extracting_claims", markdown="content")
        session.add(doc3)
        session.flush()
        doc3_id = doc3.id
    assert dc.run_document_context(doc3_id) is False
    with get_session() as session:
        doc3 = session.get(VerificationDocument, doc3_id)
        assert doc3.status == "extracting_claims"
        assert doc3.document_context is None
    print("OK")

    print("\n--- nonexistent document_id ---")
    assert dc.run_document_context(999999) is False
    print("OK")

    print("\n--- run_verification_pipeline_task actually calls run_document_context between conversion and extraction ---")
    from app.worker.celery_app import celery_app
    from app.worker import tasks

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    celery_app.conf.task_store_eager_result = True

    with get_session() as session:
        doc4 = VerificationDocument(filename="test_pipeline_context.docx", status="extracting_claims")
        session.add(doc4)
        session.flush()
        doc4_id = doc4.id

    with patch("app.ingestion.convert_docx.convert_uploaded_document", return_value=True), \
         patch("app.agents.document_context.run_document_context", return_value=True) as mock_context, \
         patch("app.agents.extract_claims.run_claim_extraction", return_value=1), \
         patch("app.agents.verify_document.verify_document_claims", return_value={"verified": 1, "failed": 0}):
        tasks.run_verification_pipeline_task.delay(doc4_id, "/fake/path.docx")
        assert mock_context.called, "the pipeline task must actually call run_document_context, not just not break"
        assert mock_context.call_args[0] == (doc4_id,)
    print("OK")

    print("\n--- rerun_verification(from_extraction=True) also refreshes document context ---")
    import app.agents.rerun_verification as rv
    with get_session() as session:
        doc5 = VerificationDocument(filename="test_rerun_context.docx", status="done", markdown="content")
        session.add(doc5)
        session.flush()
        doc5_id = doc5.id

    with patch("app.agents.rerun_verification.run_document_context", return_value=True) as mock_context2, \
         patch.object(rv, "run_claim_extraction", return_value=1), \
         patch.object(rv, "verify_document_claims", return_value={"verified": 1, "failed": 0}):
        rv.rerun_verification(doc5_id, from_extraction=True)
        assert mock_context2.called
        assert mock_context2.call_args[0] == (doc5_id,)
    print("OK")

    print("\n--- rerun_verification(from_extraction=False) does NOT refresh document context ---")
    with patch("app.agents.rerun_verification.run_document_context") as mock_context3, \
         patch.object(rv, "verify_document_claims", return_value={"verified": 0, "failed": 0}):
        rv.rerun_verification(doc5_id, from_extraction=False)
        assert not mock_context3.called, "verify-only rerun should not touch document context either"
    print("OK")

    with get_session() as session:
        for did in (doc_id, doc2_id, doc3_id, doc4_id, doc5_id):
            d = session.get(VerificationDocument, did)
            if d is not None:
                session.delete(d)
finally:
    dc.get_document_context = original_get_context

print("\nAll document_context assertions passed.")