import sys, json, random, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM
from app.db.session import get_session
from app.models.paper import Paper
from app.models.chat import Chat, Message, Citation
from app.ingestion.embed_upload import stable_point_id
import app.ingestion.delete_paper as dp_module

SOURCE_KEY = "test_delete_paper_regression"
OTHER_KEY = "test_delete_paper_regression_other"

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    chunks_dir = tmp_path / "chunks"
    pdf_dir = tmp_path / "pdfs"
    chunks_dir.mkdir()
    pdf_dir.mkdir()

    qdrant = QdrantClient(":memory:")
    qdrant.create_collection("paper_library", vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

    original_qdrant_client = dp_module.QdrantClient
    original_chunks_dir = dp_module.PAPERS_CHUNKS_DIR
    original_pdf_dir = dp_module.PAPER_PDF_DIR
    dp_module.QdrantClient = lambda url, api_key: qdrant
    dp_module.PAPERS_CHUNKS_DIR = chunks_dir
    dp_module.PAPER_PDF_DIR = pdf_dir

    try:
        target_points = [
            PointStruct(id=stable_point_id(f"{SOURCE_KEY}::{i}"),
                        vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": SOURCE_KEY, "text": f"chunk {i}"})
            for i in range(3)
        ]
        other_points = [
            PointStruct(id=stable_point_id(f"{OTHER_KEY}::{i}"),
                        vector=[random.random() for _ in range(EMBEDDING_DIM)],
                        payload={"source": OTHER_KEY, "text": f"other chunk {i}"})
            for i in range(2)
        ]
        qdrant.upsert(collection_name="paper_library", points=target_points + other_points)

        (chunks_dir / f"{SOURCE_KEY}.jsonl").write_text("{}\n")
        (chunks_dir / f"{OTHER_KEY}.jsonl").write_text("{}\n")
        (chunks_dir / ".manifest.json").write_text(json.dumps({
            SOURCE_KEY: {"pdf_sha256": "a", "settings": {}},
            OTHER_KEY: {"pdf_sha256": "b", "settings": {}},
        }))
        (pdf_dir / f"{SOURCE_KEY}.pdf").write_text("fake pdf")

        with get_session() as session:
            for key in (SOURCE_KEY, OTHER_KEY):
                existing = session.query(Paper).filter_by(source_key=key).one_or_none()
                if existing is not None:
                    session.delete(existing)

        with get_session() as session:
            paper = Paper(source_key=SOURCE_KEY, title="Delete Regression Paper", year=2026)
            session.add(paper)
            session.add(Paper(source_key=OTHER_KEY, title="Other Paper", year=2025))
            session.flush()
            chat = Chat(title="delete paper regression chat")
            session.add(chat)
            session.flush()
            msg = Message(chat_id=chat.id, role="assistant", content="cites the paper to be deleted")
            session.add(msg)
            session.flush()
            session.add(Citation(message_id=msg.id, paper_id=paper.id, apa_text="(Delete Regression, 2026)", order_index=0))
            msg_id = msg.id

        result = dp_module.delete_paper(SOURCE_KEY, delete_pdf=False)
        assert result["vectors_deleted"] == 3
        assert result["chunk_file_deleted"] is True
        assert result["manifest_entry_removed"] is True
        assert result["pdf_deleted"] is False
        assert result["db_row_deleted"] is True
        print("delete_paper() summary assertions passed.")

        assert qdrant.count("paper_library").count == 2, "the other paper's vectors must survive untouched"
        assert (chunks_dir / f"{OTHER_KEY}.jsonl").exists()
        manifest = json.loads((chunks_dir / ".manifest.json").read_text())
        assert OTHER_KEY in manifest and SOURCE_KEY not in manifest
        assert (pdf_dir / f"{SOURCE_KEY}.pdf").exists(), "delete_pdf=False must leave the PDF alone"
        print("Other paper's data confirmed untouched.")

        with get_session() as session:
            msg = session.get(Message, msg_id)
            citation = msg.citations[0]
            assert citation.paper_id is None
            assert citation.apa_text == "(Delete Regression, 2026)"
            assert session.query(Paper).filter_by(source_key=SOURCE_KEY).one_or_none() is None
        print("Citation survival + paper_id SET NULL confirmed.")

        result2 = dp_module.delete_paper(SOURCE_KEY, delete_pdf=False)
        assert result2 == {
            "source_key": SOURCE_KEY, "vectors_deleted": 0, "chunk_file_deleted": False,
            "manifest_entry_removed": False, "pdf_deleted": False, "db_row_deleted": False,
        }
        print("Idempotent re-run confirmed (safe no-op, not an error).")

        with get_session() as session:
            paper = session.query(Paper).filter_by(source_key=OTHER_KEY).one_or_none()
            if paper is not None:
                session.delete(paper)
            chat = session.query(Chat).filter_by(title="delete paper regression chat").one_or_none()
            if chat is not None:
                session.delete(chat)
    finally:
        dp_module.QdrantClient = original_qdrant_client
        dp_module.PAPERS_CHUNKS_DIR = original_chunks_dir
        dp_module.PAPER_PDF_DIR = original_pdf_dir

print("\nAll delete_paper assertions passed.")