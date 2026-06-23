import sys
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.models.paper import Paper
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimEvidence
from app.auth.security import hash_password

BOOK_KEY = "test_verification_models_book"
PAPER_KEY = "test_verification_models_paper"
USER_EMAIL = "test_verification_models_user@example.com"

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)
    existing_user = session.query(User).filter_by(email=USER_EMAIL).one_or_none()
    if existing_user is not None:
        session.delete(existing_user)

with get_session() as session:
    user = User(email=USER_EMAIL, password_hash=hash_password("testpass123"), is_admin=False)
    book = Book(source_key=BOOK_KEY, title="Verification Test Book", year=2020,
                bibliography_verified=True, page_mode="labeled")
    paper = Paper(source_key=PAPER_KEY, title="Verification Test Paper", year=2026)
    session.add_all([user, book, paper])
    session.flush()

    doc = VerificationDocument(user_id=user.id, filename="thesis_draft.docx", status="uploaded")
    session.add(doc)
    session.flush()

    claim = ExtractedClaim(document_id=doc.id, text="AI adoption has doubled since 2023.", order_index=0)
    session.add(claim)
    session.flush()

    verif = ClaimVerification(
        claim_id=claim.id, verdict="partially_supported", confidence="medium",
        explanation="The corpus supports growth, not specifically a doubling.",
    )
    session.add(verif)
    session.flush()

    # The exact mixed-source scenario this design exists for: one
    # verification, evidence from a book, a paper, AND the web all at once.
    session.add_all([
        ClaimEvidence(verification_id=verif.id, book_id=book.id, excerpt="Adoption rose significantly.", locator="p. 12", order_index=0),
        ClaimEvidence(verification_id=verif.id, paper_id=paper.id, excerpt="42% of code is AI-assisted.", locator="p. 3", order_index=1),
        ClaimEvidence(verification_id=verif.id, web_url="https://example.com/report", web_title="2026 Report",
                       excerpt="Adoption grew, but not at the rate claimed.", order_index=2),
    ])
    session.flush()

    doc_id, book_id, paper_id, verif_id = doc.id, book.id, paper.id, verif.id

print("--- full chain resolves correctly via relationships ---")
with get_session() as session:
    doc = session.get(VerificationDocument, doc_id)
    assert len(doc.claims) == 1
    c1 = doc.claims[0]
    assert c1.verification.verdict == "partially_supported"
    assert c1.verification.confidence == "medium"
    assert len(c1.verification.evidence) == 3
    assert c1.verification.evidence[0].book.title == "Verification Test Book"
    assert c1.verification.evidence[1].paper.title == "Verification Test Paper"
    assert c1.verification.evidence[2].web_title == "2026 Report"
    assert c1.verification.evidence[2].book is None and c1.verification.evidence[2].paper is None
print("OK")

print("\n--- deleting the document cascades all the way down ---")
with get_session() as session:
    session.delete(session.get(VerificationDocument, doc_id))

with get_session() as session:
    assert session.get(VerificationDocument, doc_id) is None
    assert session.query(ExtractedClaim).filter_by(document_id=doc_id).count() == 0
    assert session.query(ClaimVerification).filter_by(id=verif_id).one_or_none() is None
    assert session.query(ClaimEvidence).filter_by(verification_id=verif_id).count() == 0
print("OK")

print("\n--- deleting a Book leaves existing evidence intact, just unlinked (SET NULL) ---")
with get_session() as session:
    doc2 = VerificationDocument(filename="test2.docx", status="uploaded")
    session.add(doc2)
    session.flush()
    claim2 = ExtractedClaim(document_id=doc2.id, text="another claim", order_index=0)
    session.add(claim2)
    session.flush()
    verif2 = ClaimVerification(claim_id=claim2.id, verdict="supported", confidence="high", explanation="test")
    session.add(verif2)
    session.flush()
    ev = ClaimEvidence(verification_id=verif2.id, book_id=book_id, excerpt="some excerpt", order_index=0)
    session.add(ev)
    session.flush()
    ev_id, doc2_id = ev.id, doc2.id

with get_session() as session:
    session.delete(session.get(Book, book_id))

with get_session() as session:
    ev = session.get(ClaimEvidence, ev_id)
    assert ev is not None, "evidence must survive the book's deletion"
    assert ev.book_id is None
    assert ev.excerpt == "some excerpt"
    session.delete(session.get(VerificationDocument, doc2_id))
print("OK")

with get_session() as session:
    paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if paper is not None:
        session.delete(paper)
    user = session.query(User).filter_by(email=USER_EMAIL).one_or_none()
    if user is not None:
        session.delete(user)

print("\nAll verification model assertions passed.")