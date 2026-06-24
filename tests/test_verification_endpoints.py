import sys, io, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from unittest.mock import patch

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.auth.security import hash_password
from app.worker.celery_app import celery_app
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimEvidence
import app.ingestion.convert_docx as cd

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

EMAIL_A = "test_verification_endpoints_a@example.com"
EMAIL_B = "test_verification_endpoints_b@example.com"
BOOK_KEY = "test_verification_endpoints_book"

with tempfile.TemporaryDirectory() as tmp:
    original_uploads_dir = cd.VERIFICATION_UPLOADS_DIR
    cd.VERIFICATION_UPLOADS_DIR = Path(tmp)

    try:
        with get_session() as session:
            for email in (EMAIL_A, EMAIL_B):
                user = session.query(User).filter_by(email=email).one_or_none()
                if user is not None:
                    session.delete(user)
            book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
            if book is not None:
                session.delete(book)

        with get_session() as session:
            session.add(User(email=EMAIL_A, password_hash=hash_password("testpass123"), is_admin=False))
            session.add(User(email=EMAIL_B, password_hash=hash_password("testpass123"), is_admin=False))
            session.add(Book(source_key=BOOK_KEY, title="Endpoint Test Book", bibliography_verified=True, page_mode="labeled"))

        app = create_app()
        client = app.test_client()
        token_a = client.post("/api/v1/auth/login", json={"email": EMAIL_A, "password": "testpass123"}).get_json()["access_token"]
        token_b = client.post("/api/v1/auth/login", json={"email": EMAIL_B, "password": "testpass123"}).get_json()["access_token"]
        h_a = {"Authorization": f"Bearer {token_a}"}
        h_b = {"Authorization": f"Bearer {token_b}"}

        with patch("app.ingestion.convert_docx.convert_uploaded_document", return_value=True), \
             patch("app.agents.extract_claims.run_claim_extraction", return_value=0), \
             patch("app.agents.verify_document.verify_document_claims", return_value={"verified": 0, "failed": 0}):

            print("--- non-docx file: 400 ---")
            r = client.post("/api/v1/verification/", data={"file": (io.BytesIO(b"not a docx"), "notes.txt")},
                             content_type="multipart/form-data", headers=h_a)
            assert r.status_code == 400
            print("OK")

            print("\n--- no file: 400 ---")
            r = client.post("/api/v1/verification/", data={}, content_type="multipart/form-data", headers=h_a)
            assert r.status_code == 400
            print("OK")

            print("\n--- no auth: 401 ---")
            assert client.get("/api/v1/verification/").status_code == 401
            print("OK")

            print("\n--- user A uploads two documents, user B uploads one ---")
            r1 = client.post("/api/v1/verification/", data={"file": (io.BytesIO(b"doc one"), "doc_one.docx")},
                              content_type="multipart/form-data", headers=h_a)
            r2 = client.post("/api/v1/verification/", data={"file": (io.BytesIO(b"doc two"), "doc_two.docx")},
                              content_type="multipart/form-data", headers=h_a)
            assert r1.status_code == 202 and r2.status_code == 202
            doc1_id = int(r1.get_json()["source_key"])
            doc2_id = int(r2.get_json()["source_key"])

            r3 = client.post("/api/v1/verification/", data={"file": (io.BytesIO(b"doc three"), "doc_three.docx")},
                              content_type="multipart/form-data", headers=h_b)
            doc3_id = int(r3.get_json()["source_key"])
            print("OK")

        print("\n--- GET list is scoped per user ---")
        r = client.get("/api/v1/verification/", headers=h_a)
        assert {d["filename"] for d in r.get_json()} == {"doc_one.docx", "doc_two.docx"}
        r = client.get("/api/v1/verification/", headers=h_b)
        assert {d["filename"] for d in r.get_json()} == {"doc_three.docx"}
        print("OK")

        print("\n--- detail response resolves book/web evidence correctly ---")
        with get_session() as session:
            book = session.query(Book).filter_by(source_key=BOOK_KEY).one()
            claim = ExtractedClaim(document_id=doc1_id, text="AI adoption doubled.", order_index=0)
            session.add(claim)
            session.flush()
            verif = ClaimVerification(claim_id=claim.id, verdict="partially_supported", confidence="medium", explanation="test")
            session.add(verif)
            session.flush()
            session.add(ClaimEvidence(verification_id=verif.id, book_id=book.id, excerpt="book excerpt", locator="p. 9", order_index=0))
            session.add(ClaimEvidence(verification_id=verif.id, web_url="https://example.com", web_title="Web Source", excerpt="web excerpt", order_index=1))

        r = client.get(f"/api/v1/verification/{doc1_id}", headers=h_a)
        assert r.status_code == 200
        body = r.get_json()
        assert body["claim_count"] == 1
        claim_body = body["claims"][0]
        assert claim_body["verification"]["verdict"] == "partially_supported"
        evidence = claim_body["verification"]["evidence"]
        book_evidence = next(e for e in evidence if e["book_id"] is not None)
        web_evidence = next(e for e in evidence if e["web_url"] is not None)
        assert book_evidence["title"] == "Endpoint Test Book"
        assert web_evidence["title"] == "Web Source"
        print("OK")

        print("\n--- ownership: user B gets 404 (not 403) on user A's document ---")
        r = client.get(f"/api/v1/verification/{doc1_id}", headers=h_b)
        assert r.status_code == 404
        print("OK")

        print("\n--- ownership: user B cannot delete user A's document ---")
        r = client.delete(f"/api/v1/verification/{doc1_id}", headers=h_b)
        assert r.status_code == 404
        with get_session() as session:
            assert session.get(VerificationDocument, doc1_id) is not None
        print("OK")

        print("\n--- owner can delete their own document ---")
        r = client.delete(f"/api/v1/verification/{doc1_id}", headers=h_a)
        assert r.status_code == 204
        with get_session() as session:
            assert session.get(VerificationDocument, doc1_id) is None
        print("OK")

        with get_session() as session:
            for did in (doc2_id, doc3_id):
                doc = session.get(VerificationDocument, did)
                if doc is not None:
                    session.delete(doc)
            book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
            if book is not None:
                session.delete(book)
            for email in (EMAIL_A, EMAIL_B):
                user = session.query(User).filter_by(email=email).one_or_none()
                if user is not None:
                    session.delete(user)
    finally:
        cd.VERIFICATION_UPLOADS_DIR = original_uploads_dir

print("\nAll verification-endpoint assertions passed.")