import sys
sys.path.insert(0, ".")

import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from unittest.mock import patch

from app.worker.celery_app import celery_app
from app.worker import tasks
from app.db.session import get_session
from app.models.verification import VerificationDocument

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

with get_session() as session:
    doc = VerificationDocument(filename="test_pipeline_task.docx", status="extracting_claims")
    session.add(doc)
    session.flush()
    doc_id = doc.id

print("--- full success: convert, extract, and verify all called in order ---")
with patch("app.ingestion.convert_docx.convert_uploaded_document", return_value=True) as mock_convert, \
     patch("app.agents.extract_claims.run_claim_extraction", return_value=3) as mock_extract, \
     patch("app.agents.verify_document.verify_document_claims",
           return_value={"document_id": doc_id, "verified": 3, "failed": 0}) as mock_verify:
    result = tasks.run_verification_pipeline_task.delay(doc_id, "/fake/path.docx")
    body = result.get()
    assert mock_convert.called and mock_extract.called and mock_verify.called
    assert body["succeeded"] is True
    assert body["verified"] == 3
print("OK")

print("\n--- conversion fails: extraction and verification never run ---")
with patch("app.ingestion.convert_docx.convert_uploaded_document", return_value=False) as mock_convert2, \
     patch("app.agents.extract_claims.run_claim_extraction") as mock_extract2, \
     patch("app.agents.verify_document.verify_document_claims") as mock_verify2:
    result2 = tasks.run_verification_pipeline_task.delay(doc_id, "/fake/path.docx")
    body2 = result2.get()
    assert mock_convert2.called
    assert not mock_extract2.called
    assert not mock_verify2.called
    assert body2["stage"] == "converting"
    assert body2["succeeded"] is False
print("OK")

print("\n--- extraction fails (document status becomes 'failed'): verification never runs ---")
with patch("app.ingestion.convert_docx.convert_uploaded_document", return_value=True), \
     patch("app.agents.extract_claims.run_claim_extraction", return_value=0), \
     patch("app.agents.verify_document.verify_document_claims") as mock_verify3:
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        doc.status = "failed"
    result3 = tasks.run_verification_pipeline_task.delay(doc_id, "/fake/path.docx")
    body3 = result3.get()
    assert not mock_verify3.called
    assert body3["stage"] == "extracting_claims"
    assert body3["succeeded"] is False
print("OK")

with get_session() as session:
    session.delete(session.get(VerificationDocument, doc_id))

print("\nAll run_verification_pipeline_task assertions passed.")