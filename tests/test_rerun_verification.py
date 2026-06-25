import sys
sys.path.insert(0, ".")

import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from unittest.mock import patch

from app.db.session import get_session
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimEvidence
import app.agents.rerun_verification as rv
from app.worker.celery_app import celery_app
from app.worker import tasks

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

original_extraction = rv.run_claim_extraction
original_verify = rv.verify_document_claims

try:
    print("--- from_extraction=True: old claims deleted (cascading), fresh ones extracted ---")
    with get_session() as session:
        doc = VerificationDocument(filename="test_rerun_from_extraction.docx", status="done", markdown="content")
        session.add(doc)
        session.flush()
        old_claim = ExtractedClaim(document_id=doc.id, order_index=0, text="An old claim from before the fix.")
        session.add(old_claim)
        session.flush()
        old_verif = ClaimVerification(claim_id=old_claim.id, verdict="contradicted", confidence="high", explanation="old")
        session.add(old_verif)
        session.flush()
        session.add(ClaimEvidence(verification_id=old_verif.id, excerpt="old evidence", order_index=0))
        doc_id = doc.id
        old_verif_id = old_verif.id

    extraction_calls = []

    def fake_extraction(did):
        extraction_calls.append(did)
        with get_session() as session:
            d = session.get(VerificationDocument, did)
            session.add(ExtractedClaim(document_id=did, order_index=0, text="A fresh claim from the new extraction."))
            d.status = "verifying"
        return 1

    verify_calls = []

    def fake_verify(did):
        verify_calls.append(did)
        return {"verified": 1, "failed": 0}

    rv.run_claim_extraction = fake_extraction
    rv.verify_document_claims = fake_verify

    result = rv.rerun_verification(doc_id, from_extraction=True)
    assert extraction_calls == [doc_id]
    assert verify_calls == [doc_id]
    assert result == {"document_id": doc_id, "verified": 1, "failed": 0}

    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        assert [c.text for c in doc.claims] == ["A fresh claim from the new extraction."], \
            "the old claim must be gone, only the fresh one should remain"
        assert session.get(ClaimVerification, old_verif_id) is None, "old verification must cascade-delete, not be orphaned"
        session.delete(doc)
    print("OK")

    print("\n--- from_extraction=False: claims kept exactly as-is, only verifications reset ---")
    with get_session() as session:
        doc2 = VerificationDocument(filename="test_rerun_verify_only.docx", status="done", markdown="content")
        session.add(doc2)
        session.flush()
        c1 = ExtractedClaim(document_id=doc2.id, order_index=0, text="Claim one, kept as-is.")
        c2 = ExtractedClaim(document_id=doc2.id, order_index=1, text="Claim two, kept as-is.")
        session.add_all([c1, c2])
        session.flush()
        v1 = ClaimVerification(claim_id=c1.id, verdict="contradicted", confidence="high", explanation="old wrong verdict")
        session.add(v1)
        session.flush()
        session.add(ClaimEvidence(verification_id=v1.id, excerpt="old evidence", order_index=0))
        doc2_id = doc2.id
        old_v1_id = v1.id

    extraction_calls2 = []
    rv.run_claim_extraction = lambda did: extraction_calls2.append(did)
    rv.verify_document_claims = lambda did: {"verified": 2, "failed": 0}

    result2 = rv.rerun_verification(doc2_id, from_extraction=False)
    assert extraction_calls2 == [], "extraction must never run in verify-only mode"
    assert result2 == {"document_id": doc2_id, "verified": 2, "failed": 0}

    with get_session() as session:
        doc2 = session.get(VerificationDocument, doc2_id)
        texts = sorted(c.text for c in doc2.claims)
        assert texts == ["Claim one, kept as-is.", "Claim two, kept as-is."], "verify-only must never touch the claims"
        assert session.get(ClaimVerification, old_v1_id) is None, "old verification must be reset"
        assert all(c.verification is None for c in doc2.claims), "every claim should be back to pending"
        session.delete(doc2)
    print("OK")

    print("\n--- nonexistent document_id ---")
    assert rv.rerun_verification(999999) == {"document_id": 999999, "error": "document not found"}
    print("OK")

    print("\n--- document with no stored markdown ---")
    with get_session() as session:
        doc3 = VerificationDocument(filename="test_rerun_no_markdown.docx", status="failed", markdown=None)
        session.add(doc3)
        session.flush()
        doc3_id = doc3.id

    result3 = rv.rerun_verification(doc3_id)
    assert result3["error"] == "no markdown stored for this document -- cannot rerun without re-uploading"
    with get_session() as session:
        session.delete(session.get(VerificationDocument, doc3_id))
    print("OK")

    print("\n--- rerun_verification_task: wraps the function correctly, including from_extraction ---")
    with patch("app.agents.rerun_verification.rerun_verification",
               return_value={"document_id": 5, "verified": 3, "failed": 0}) as mock_rerun:
        task_result = tasks.rerun_verification_task.delay(5, from_extraction=False)
        assert task_result.get() == {"document_id": 5, "verified": 3, "failed": 0}
        assert mock_rerun.call_args[0] == (5,)
        assert mock_rerun.call_args[1]["from_extraction"] is False
    print("OK")
finally:
    rv.run_claim_extraction = original_extraction
    rv.verify_document_claims = original_verify

print("\nAll rerun_verification assertions passed.")