import sys, random, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM
from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.models.paper import Paper
from app.auth.security import hash_password
from app.api.factory import create_app
from app.worker.celery_app import celery_app
from app.ingestion.embed_upload import stable_point_id
import app.ingestion.delete_book as db_module
import app.ingestion.delete_paper as dp_module

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
# Without this, eager mode never writes to the result backend at all --
# the polling endpoint would see every job as permanently PENDING, which
# is exactly the bug a first version of this test caught.
celery_app.conf.task_store_eager_result = True

ADMIN_EMAIL = "test_admin_delete_endpoint_admin@example.com"
PLAIN_EMAIL = "test_admin_delete_endpoint_plain@example.com"
BOOK_KEY = "test_admin_delete_endpoint_book"
PAPER_KEY = "test_admin_delete_endpoint_paper"

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    chunks_dir, pdf_dir = tmp_path / "chunks", tmp_path / "pdfs"
    papers_chunks_dir, papers_pdf_dir = tmp_path / "papers_chunks", tmp_path / "papers_pdfs"
    for d in (chunks_dir, pdf_dir, papers_chunks_dir, papers_pdf_dir):
        d.mkdir()

    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("book_library", vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
    qdrant.create_collection("paper_library", vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

    originals = (db_module.QdrantClient, db_module.CHUNKS_DIR, db_module.PDF_DIR,
                 dp_module.QdrantClient, dp_module.PAPERS_CHUNKS_DIR, dp_module.PAPER_PDF_DIR)
    db_module.QdrantClient = lambda url, api_key, timeout=None: qdrant
    db_module.CHUNKS_DIR = chunks_dir
    db_module.PDF_DIR = pdf_dir
    dp_module.QdrantClient = lambda url, api_key, timeout=None: qdrant
    dp_module.PAPERS_CHUNKS_DIR = papers_chunks_dir
    dp_module.PAPER_PDF_DIR = papers_pdf_dir

    try:
        qdrant.upsert(collection_name="book_library", points=[
            PointStruct(id=stable_point_id(f"{BOOK_KEY}::0"), vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": BOOK_KEY, "text": "x"})
        ])
        qdrant.upsert(collection_name="paper_library", points=[
            PointStruct(id=stable_point_id(f"{PAPER_KEY}::0"), vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": PAPER_KEY, "text": "x"})
        ])

        with get_session() as session:
            for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
                row = session.query(cls).filter_by(source_key=key).one_or_none()
                if row is not None:
                    session.delete(row)
            for email in (ADMIN_EMAIL, PLAIN_EMAIL):
                user = session.query(User).filter_by(email=email).one_or_none()
                if user is not None:
                    session.delete(user)

        with get_session() as session:
            session.add(User(email=ADMIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=True))
            session.add(User(email=PLAIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=False))
            book = Book(source_key=BOOK_KEY, title="Endpoint Test Book", bibliography_verified=False, page_mode="labeled")
            paper = Paper(source_key=PAPER_KEY, title="Endpoint Test Paper")
            session.add(book)
            session.add(paper)
            session.flush()
            book_id, paper_id = book.id, paper.id

        app = create_app()
        client = app.test_client()

        admin_token = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
        plain_token = client.post("/api/v1/auth/login", json={"email": PLAIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
        admin_h = {"Authorization": f"Bearer {admin_token}"}
        plain_h = {"Authorization": f"Bearer {plain_token}"}

        assert client.delete(f"/api/v1/admin/books/{book_id}", headers=plain_h).status_code == 403
        assert client.delete("/api/v1/admin/books/999999", headers=admin_h).status_code == 404
        print("Auth/404 assertions passed.")

        r = client.delete(f"/api/v1/admin/books/{book_id}", headers=admin_h)
        assert r.status_code == 202
        task_id = r.get_json()["task_id"]
        assert r.get_json()["source_key"] == BOOK_KEY
        print("DELETE returns 202 with task_id.")

        r = client.get(f"/api/v1/admin/jobs/{task_id}", headers=admin_h)
        assert r.status_code == 200
        assert r.get_json()["state"] == "SUCCESS"
        assert r.get_json()["result"]["db_row_deleted"] is True
        assert r.get_json()["result"]["vectors_deleted"] == 1
        print("Job polling reports SUCCESS with the real delete summary.")

        with get_session() as session:
            assert session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none() is None

        r = client.get("/api/v1/admin/jobs/00000000-0000-0000-0000-000000000000", headers=admin_h)
        assert r.get_json()["state"] == "PENDING"
        print("Unknown task_id polls as PENDING, not an error.")

        (papers_pdf_dir / f"{PAPER_KEY}.pdf").write_text("fake")
        r = client.delete(f"/api/v1/admin/papers/{paper_id}?delete_pdf=true", headers=admin_h)
        assert r.status_code == 202
        task_id2 = r.get_json()["task_id"]
        r = client.get(f"/api/v1/admin/jobs/{task_id2}", headers=admin_h)
        assert r.get_json()["result"]["pdf_deleted"] is True
        assert not (papers_pdf_dir / f"{PAPER_KEY}.pdf").exists()
        print("Paper DELETE + delete_pdf query param confirmed.")

        with get_session() as session:
            for email in (ADMIN_EMAIL, PLAIN_EMAIL):
                user = session.query(User).filter_by(email=email).one_or_none()
                if user is not None:
                    session.delete(user)
    finally:
        (db_module.QdrantClient, db_module.CHUNKS_DIR, db_module.PDF_DIR,
         dp_module.QdrantClient, dp_module.PAPERS_CHUNKS_DIR, dp_module.PAPER_PDF_DIR) = originals

print("\nAll admin delete-endpoint assertions passed.")