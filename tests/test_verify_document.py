import sys
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.verification import VerificationDocument, ExtractedClaim
import app.agents.verify_document as vd

original_run_verification = vd.run_verification

try:
    print("--- all claims verify successfully ---")
    with get_session() as session:
        doc = VerificationDocument(filename="test_verify_doc_all_ok.docx", status="verifying")
        session.add(doc)
        session.flush()
        for i in range(3):
            session.add(ExtractedClaim(document_id=doc.id, text=f"claim {i}", order_index=i))
        doc_id = doc.id

    vd.run_verification = lambda claim_id: True
    result = vd.verify_document_claims(doc_id)
    assert result == {"document_id": doc_id, "verified": 3, "failed": 0}
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        assert doc.status == "done"
        session.delete(doc)
    print("OK")

    print("\n--- mixed success/failure still reaches done ---")
    with get_session() as session:
        doc2 = VerificationDocument(filename="test_verify_doc_mixed.docx", status="verifying")
        session.add(doc2)
        session.flush()
        claim_ids = []
        for i in range(4):
            c = ExtractedClaim(document_id=doc2.id, text=f"claim {i}", order_index=i)
            session.add(c)
            session.flush()
            claim_ids.append(c.id)
        doc2_id = doc2.id

    fail_set = {claim_ids[1], claim_ids[3]}
    vd.run_verification = lambda claim_id: claim_id not in fail_set
    result2 = vd.verify_document_claims(doc2_id)
    assert result2 == {"document_id": doc2_id, "verified": 2, "failed": 2}
    with get_session() as session:
        doc2 = session.get(VerificationDocument, doc2_id)
        assert doc2.status == "done"
        session.delete(doc2)
    print("OK")

    print("\n--- zero claims (extraction found nothing checkable): still done, 0/0 ---")
    with get_session() as session:
        doc3 = VerificationDocument(filename="test_verify_doc_no_claims.docx", status="verifying")
        session.add(doc3)
        session.flush()
        doc3_id = doc3.id

    result3 = vd.verify_document_claims(doc3_id)
    assert result3 == {"document_id": doc3_id, "verified": 0, "failed": 0}
    with get_session() as session:
        doc3 = session.get(VerificationDocument, doc3_id)
        assert doc3.status == "done"
        session.delete(doc3)
    print("OK")

    print("\n--- nonexistent document_id ---")
    result4 = vd.verify_document_claims(999999)
    assert result4["error"] == "document not found"
    print("OK")
finally:
    vd.run_verification = original_run_verification

print("\nAll verify_document_claims assertions passed.")