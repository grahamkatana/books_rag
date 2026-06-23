import sys, random, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.ingestion.embed_upload import stable_point_id
from app.worker.celery_app import celery_app
from app.worker import tasks
import app.ingestion.delete_book as db_module
import app.ingestion.delete_paper as dp_module

# Eager mode: tasks execute synchronously in-process, no real broker or
# worker needed -- Celery's own recommended way to test task logic in
# isolation. The separate, genuinely-async worker/broker plumbing itself
# (a real Redis, a real worker subprocess, state transitions, exception
# propagation across processes) was verified manually, not as part of
# this automated suite, since that needs a real worker process running
# this script can't itself manage reliably; see the project notes.
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

SOURCE_KEY_BOOK = "test_celery_task_book"
SOURCE_KEY_PAPER = "test_celery_task_paper"

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    chunks_dir = tmp_path / "chunks"
    pdf_dir = tmp_path / "pdfs"
    papers_chunks_dir = tmp_path / "papers_chunks"
    papers_pdf_dir = tmp_path / "papers_pdfs"
    for d in (chunks_dir, pdf_dir, papers_chunks_dir, papers_pdf_dir):
        d.mkdir()

    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("book_library", vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
    qdrant.create_collection("paper_library", vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

    originals = {
        "book_qdrant": db_module.QdrantClient, "book_chunks": db_module.CHUNKS_DIR, "book_pdf": db_module.PDF_DIR,
        "paper_qdrant": dp_module.QdrantClient, "paper_chunks": dp_module.PAPERS_CHUNKS_DIR, "paper_pdf": dp_module.PAPER_PDF_DIR,
    }
    db_module.QdrantClient = lambda url, api_key, timeout=None: qdrant
    db_module.CHUNKS_DIR = chunks_dir
    db_module.PDF_DIR = pdf_dir
    dp_module.QdrantClient = lambda url, api_key, timeout=None: qdrant
    dp_module.PAPERS_CHUNKS_DIR = papers_chunks_dir
    dp_module.PAPER_PDF_DIR = papers_pdf_dir

    try:
        qdrant.upsert(collection_name="book_library", points=[
            PointStruct(id=stable_point_id(f"{SOURCE_KEY_BOOK}::0"), vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": SOURCE_KEY_BOOK, "text": "chunk"})
        ])
        qdrant.upsert(collection_name="paper_library", points=[
            PointStruct(id=stable_point_id(f"{SOURCE_KEY_PAPER}::0"), vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": SOURCE_KEY_PAPER, "text": "chunk"})
        ])

        with get_session() as session:
            existing = session.query(Book).filter_by(source_key=SOURCE_KEY_BOOK).one_or_none()
            if existing is not None:
                session.delete(existing)
            existing = session.query(Paper).filter_by(source_key=SOURCE_KEY_PAPER).one_or_none()
            if existing is not None:
                session.delete(existing)

        with get_session() as session:
            session.add(Book(source_key=SOURCE_KEY_BOOK, title="Celery Task Test Book",
                              bibliography_verified=False, page_mode="labeled"))
            session.add(Paper(source_key=SOURCE_KEY_PAPER, title="Celery Task Test Paper"))

        print("--- delete_book_task ---")
        async_result = tasks.delete_book_task.delay(SOURCE_KEY_BOOK, delete_pdf=False)
        assert async_result.state == "SUCCESS"
        result = async_result.get()
        assert result["vectors_deleted"] == 1
        assert result["db_row_deleted"] is True
        with get_session() as session:
            assert session.query(Book).filter_by(source_key=SOURCE_KEY_BOOK).one_or_none() is None
        print("OK")

        print("\n--- delete_paper_task ---")
        async_result = tasks.delete_paper_task.delay(SOURCE_KEY_PAPER, delete_pdf=False)
        assert async_result.state == "SUCCESS"
        result = async_result.get()
        assert result["vectors_deleted"] == 1
        assert result["db_row_deleted"] is True
        with get_session() as session:
            assert session.query(Paper).filter_by(source_key=SOURCE_KEY_PAPER).one_or_none() is None
        print("OK")

        print("\n--- a task against an already-deleted source is a safe no-op via the task interface too ---")
        async_result = tasks.delete_book_task.delay(SOURCE_KEY_BOOK, delete_pdf=False)
        result = async_result.get()
        assert result["db_row_deleted"] is False
        print("OK")
    finally:
        db_module.QdrantClient = originals["book_qdrant"]
        db_module.CHUNKS_DIR = originals["book_chunks"]
        db_module.PDF_DIR = originals["book_pdf"]
        dp_module.QdrantClient = originals["paper_qdrant"]
        dp_module.PAPERS_CHUNKS_DIR = originals["paper_chunks"]
        dp_module.PAPER_PDF_DIR = originals["paper_pdf"]

print("\nAll Celery task assertions passed.")