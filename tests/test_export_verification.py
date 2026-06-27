import sys, tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.db.session import get_session
from app.models.book import Book
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimEvidence
import export_verification_report as report_script

BOOK_KEY = "test_export_report_book"
FILENAME = "test_export_report_doc.docx"

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)
    existing_doc = session.query(VerificationDocument).filter_by(filename=FILENAME).one_or_none()
    if existing_doc is not None:
        session.delete(existing_doc)

with get_session() as session:
    book = Book(source_key=BOOK_KEY, title="Software Engineering", year=2020,
                bibliography_verified=True, page_mode="labeled")
    session.add(book)
    session.flush()

    markdown = (
        "# Chapter\n\n"
        "A supported claim that matches the text exactly.\n\n"
        "Just framing prose, not a checkable claim at all.\n\n"
        "A claim that does NOT match because it was rephrased.\n\n"
        "A partially supported claim with real book evidence.\n\n"
        "A claim whose verification errored out.\n\n"
        "A claim that is still pending, not yet verified."
    )

    doc = VerificationDocument(filename=FILENAME, status="done", markdown=markdown)
    session.add(doc)
    session.flush()

    c_supported = ExtractedClaim(document_id=doc.id, order_index=0, text="A supported claim that matches the text exactly.")
    c_unmatched = ExtractedClaim(document_id=doc.id, order_index=1, text="A claim that was REPHRASED and will not match.")
    c_partial = ExtractedClaim(document_id=doc.id, order_index=2, text="A partially supported claim with real book evidence.")
    c_error = ExtractedClaim(document_id=doc.id, order_index=3, text="A claim whose verification errored out.")
    c_pending = ExtractedClaim(document_id=doc.id, order_index=4, text="A claim that is still pending, not yet verified.")
    session.add_all([c_supported, c_unmatched, c_partial, c_error, c_pending])
    session.flush()

    v1 = ClaimVerification(claim_id=c_supported.id, verdict="supported", confidence="high", explanation="Confirmed.")
    session.add(v1)
    session.flush()
    session.add(ClaimEvidence(verification_id=v1.id, web_url="https://example.com", web_title="A Source",
                               excerpt="supporting excerpt", order_index=0))

    v2 = ClaimVerification(claim_id=c_partial.id, verdict="partially_supported", confidence="medium", explanation="Partial.")
    session.add(v2)
    session.flush()
    session.add(ClaimEvidence(verification_id=v2.id, book_id=book.id, locator="p. 10",
                               excerpt="book excerpt", order_index=0))

    v3 = ClaimVerification(claim_id=c_error.id, verdict="error", confidence="low", explanation="Verification failed: simulated")
    session.add(v3)

    doc_id = doc.id

from app.api.v1.serializers import verification_document_to_detail_dict
with get_session() as session:
    doc_dict = verification_document_to_detail_dict(session.get(VerificationDocument, doc_id))

report = report_script.build_report(doc_dict)

print("--- matched claims are bolded and footnote-marked inline ---")
assert "**A supported claim that matches the text exactly.**[^" in report
assert "**A partially supported claim with real book evidence.**[^" in report
assert "**A claim whose verification errored out.**[^" in report
print("OK")

print("\n--- the unmatched (rephrased) claim is NOT inline-marked, but still has its own section ---")
assert "A claim that was REPHRASED" not in report.split("## Claims & Verdicts")[0], \
    "the unmatched claim's text must not appear bolded/marked in the annotated section"
assert "A claim that was REPHRASED" in report.split("## Claims & Verdicts")[1]
assert "not found verbatim" in report
print("OK")

print("\n--- verdicts render distinctly: supported, partially supported, and error are not conflated ---")
assert "SUPPORTED  (high confidence)" in report
assert "PARTIALLY SUPPORTED  (medium confidence)" in report
assert "VERIFICATION FAILED  (low confidence)" in report
print("OK")

print("\n--- pending (never verified) claim is distinguished from a failed one ---")
assert "still pending -- not yet verified." in report
print("OK")

print("\n--- evidence renders correctly for both book and web sources ---")
assert "Software Engineering, p. 10" in report
assert "[https://example.com](https://example.com)" in report
print("OK")

print("\n--- header stats are accurate ---")
assert "5 total, 3 verified, 4 matched to a specific spot" in report
print("OK")

print("\n--- zero-claims document ---")
with tempfile.TemporaryDirectory():
    empty_dict = {
        "id": 999, "filename": "empty.docx", "status": "done", "error_message": None,
        "created_at": None, "claim_count": 0, "markdown": "Just text.", "claims": [],
    }
    empty_report = report_script.build_report(empty_dict)
    assert "No checkable claims were extracted" in empty_report
print("OK")

print("\n--- cross-check rendering: disagreement is shown distinctly ---")
cross_check_dict = {
    "id": 1, "filename": "cc.docx", "status": "done", "error_message": None, "created_at": None,
    "claim_count": 1, "markdown": "A claim.",
    "claims": [{
        "id": 1, "text": "A claim.", "order_index": 0,
        "verification": {
            "verdict": "supported", "confidence": "high", "explanation": "Original take.", "evidence": [],
            "cross_check": {
                "agrees": False, "verdict": "unverifiable", "confidence": "medium",
                "explanation": "The evidence does not actually address this.",
                "is_checkable_claim": True, "model": "claude-sonnet-4-6",
            },
        },
    }],
}
cc_report = report_script.build_report(cross_check_dict)
assert "**Cross-checked:** 1 claim(s), 1 disagreement(s)" in cc_report
assert "Cross-check (claude-sonnet-4-6): DISAGREES" in cc_report
assert "its own verdict: UNVERIFIABLE" in cc_report
assert "Flagged: the cross-check model judges" not in cc_report
print("OK")

print("\n--- cross-check rendering: not-checkable flag shown when triggered ---")
cross_check_dict["claims"][0]["verification"]["cross_check"]["is_checkable_claim"] = False
flagged_report = report_script.build_report(cross_check_dict)
assert "Flagged: the cross-check model judges this isn" in flagged_report
print("OK")

with get_session() as session:
    doc = session.query(VerificationDocument).filter_by(filename=FILENAME).one_or_none()
    if doc is not None:
        session.delete(doc)
    book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if book is not None:
        session.delete(book)

print("\nAll export_verification_report assertions passed.")