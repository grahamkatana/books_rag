import sys
sys.path.insert(0, ".")

import os
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-test-key")
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from pydantic_ai.models.test import TestModel

from app.db.session import get_session
from app.models.book import Book
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimEvidence, ClaimCrossCheck
import app.agents.cross_check_claim as cc

BOOK_KEY = "test_cross_check_book"

with get_session() as session:
    existing = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)

# --- format_verification_for_review: pure logic, reuses the existing serializer ---
print("--- format_verification_for_review ---")
with get_session() as session:
    book = Book(source_key=BOOK_KEY, title="Test Book", bibliography_verified=True, page_mode="labeled")
    session.add(book)
    session.flush()
    doc = VerificationDocument(filename="test_cross_check_doc.docx", status="done")
    session.add(doc)
    session.flush()
    claim = ExtractedClaim(document_id=doc.id, order_index=0, text="AI adoption doubled since 2023.")
    session.add(claim)
    session.flush()
    verif = ClaimVerification(claim_id=claim.id, verdict="supported", confidence="high", explanation="Confirmed by the survey.")
    session.add(verif)
    session.flush()
    session.add(ClaimEvidence(verification_id=verif.id, book_id=book.id, locator="p. 5", excerpt="Adoption figures doubled.", order_index=0))
    doc_id, claim_id, verif_id = doc.id, claim.id, verif.id

with get_session() as session:
    claim = session.get(ExtractedClaim, claim_id)
    prompt = cc.format_verification_for_review(claim.text, claim.verification)
assert "AI adoption doubled since 2023." in prompt
assert "supported (high confidence)" in prompt
assert "Test Book, p. 5" in prompt
assert "Adoption figures doubled." in prompt
print("OK")

# --- agent plumbing, via pydantic-ai's own TestModel, no real API call ---
print("\n--- cross_check_claim_text agent plumbing ---")
agent = cc.build_cross_check_agent()
fake_result = cc.CrossCheckResult(agrees=True, verdict="supported", confidence="high", explanation="Agreed.", is_checkable_claim=True)
with agent.override(model=TestModel(custom_output_args=fake_result.model_dump())):
    result = cc.cross_check_claim_text("some review prompt", agent=agent)
assert result.agrees is True
assert result.verdict == "supported"
print("OK")

original_cross_check_claim_text = cc.cross_check_claim_text
try:
    print("\n--- run_cross_check: persists a real row ---")
    cc.cross_check_claim_text = lambda prompt, agent=None: cc.CrossCheckResult(
        agrees=False, verdict="unverifiable", confidence="medium",
        explanation="The evidence does not actually address this.", is_checkable_claim=False,
    )
    assert cc.run_cross_check(claim_id) is True
    with get_session() as session:
        verif = session.get(ClaimVerification, verif_id)
        assert verif.cross_check is not None
        assert verif.cross_check.agrees is False
        assert verif.cross_check.verdict == "unverifiable"
        assert verif.cross_check.is_checkable_claim is False
    print("OK")

    print("\n--- re-running replaces the old cross-check row, never accumulates ---")
    cc.cross_check_claim_text = lambda prompt, agent=None: cc.CrossCheckResult(
        agrees=True, verdict="supported", confidence="high", explanation="second pass", is_checkable_claim=True,
    )
    assert cc.run_cross_check(claim_id) is True
    with get_session() as session:
        verif = session.get(ClaimVerification, verif_id)
        assert verif.cross_check.agrees is True
        assert verif.cross_check.explanation == "second pass"
        assert session.query(ClaimCrossCheck).filter_by(verification_id=verif_id).count() == 1
    print("OK")

    print("\n--- claim with no verification yet: fails cleanly ---")
    with get_session() as session:
        unverified = ExtractedClaim(document_id=doc_id, order_index=1, text="Not yet verified.")
        session.add(unverified)
        session.flush()
        unverified_id = unverified.id
    assert cc.run_cross_check(unverified_id) is False
    print("OK")

    print("\n--- nonexistent claim_id ---")
    assert cc.run_cross_check(999999) is False
    print("OK")

    print("\n--- agent call raises: returns False, no row written ---")
    def raise_err(prompt, agent=None):
        raise RuntimeError("simulated failure")
    cc.cross_check_claim_text = raise_err
    with get_session() as session:
        claim_fail = ExtractedClaim(document_id=doc_id, order_index=2, text="Will fail to cross-check.")
        session.add(claim_fail)
        session.flush()
        v_fail = ClaimVerification(claim_id=claim_fail.id, verdict="supported", confidence="high", explanation="x")
        session.add(v_fail)
        session.flush()
        claim_fail_id = claim_fail.id
    assert cc.run_cross_check(claim_fail_id) is False
    with get_session() as session:
        claim_fail = session.get(ExtractedClaim, claim_fail_id)
        assert claim_fail.verification.cross_check is None
    print("OK")

    print("\n--- cross_check_document: skips error verdicts and unverified claims, filters by verdicts_to_check ---")
    with get_session() as session:
        doc2 = VerificationDocument(filename="test_cc_doc2.docx", status="done")
        session.add(doc2)
        session.flush()
        c_supported = ExtractedClaim(document_id=doc2.id, order_index=0, text="Supported claim.")
        c_contradicted = ExtractedClaim(document_id=doc2.id, order_index=1, text="Contradicted claim.")
        c_error = ExtractedClaim(document_id=doc2.id, order_index=2, text="Errored claim.")
        c_pending = ExtractedClaim(document_id=doc2.id, order_index=3, text="Pending claim.")
        session.add_all([c_supported, c_contradicted, c_error, c_pending])
        session.flush()
        session.add(ClaimVerification(claim_id=c_supported.id, verdict="supported", confidence="high", explanation="x"))
        session.add(ClaimVerification(claim_id=c_contradicted.id, verdict="contradicted", confidence="high", explanation="x"))
        session.add(ClaimVerification(claim_id=c_error.id, verdict="error", confidence="low", explanation="Verification failed: x"))
        doc2_id = doc2.id

    def fake_run_cross_check(claim_id_arg):
        with get_session() as session:
            claim = session.get(ExtractedClaim, claim_id_arg)
            if claim.verification.cross_check is not None:
                session.delete(claim.verification.cross_check)
                session.flush()
            session.add(ClaimCrossCheck(verification_id=claim.verification.id, agrees=True, verdict=claim.verification.verdict,
                                         confidence="high", explanation="fake", is_checkable_claim=True, model="test"))
        return True

    cc.run_cross_check = fake_run_cross_check
    result = cc.cross_check_document(doc2_id)
    assert result["checked"] == 2, "only supported + contradicted are reviewable; error and pending must be excluded"
    assert result["agreed"] == 2

    with get_session() as session:
        doc2 = session.get(VerificationDocument, doc2_id)
        by_text = {c.text: c for c in doc2.claims}
        assert by_text["Errored claim."].verification.cross_check is None
        assert by_text["Pending claim."].verification is None
        session.delete(doc2)
    print("OK")

    print("\n--- nonexistent document ---")
    assert cc.cross_check_document(999999) == {"document_id": 999999, "error": "document not found"}
    print("OK")
finally:
    cc.cross_check_claim_text = original_cross_check_claim_text

with get_session() as session:
    session.delete(session.get(VerificationDocument, doc_id))
    book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if book is not None:
        session.delete(book)

print("\nAll cross_check_claim assertions passed.")