import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from app.ingestion import chunk_papers as cp


class FakeProv:
    def __init__(self, page_no): self.page_no = page_no


class FakeDocItem:
    def __init__(self, provs): self.prov = provs


class FakeMeta:
    def __init__(self, doc_items=None, headings=None):
        self.doc_items = doc_items or []
        self.headings = headings or []


class FakeChunk:
    def __init__(self, meta): self.meta = meta


class FakeChunker:
    def contextualize(self, chunk):
        return "fake contextualized text"


# --- extract_page_no ---
assert cp.extract_page_no(FakeChunk(FakeMeta(doc_items=[FakeDocItem([FakeProv(7)])]))) == 7
assert cp.extract_page_no(FakeChunk(FakeMeta(doc_items=[FakeDocItem([]), FakeDocItem([FakeProv(12)])]))) == 12
assert cp.extract_page_no(FakeChunk(FakeMeta(doc_items=[]))) is None
assert cp.extract_page_no(FakeChunk(FakeMeta())) is None
print("extract_page_no assertions passed.")

# --- extract_section ---
assert cp.extract_section(FakeChunk(FakeMeta(headings=["Related Work", "Agentic Architectures"]))) == "Related Work > Agentic Architectures"
assert cp.extract_section(FakeChunk(FakeMeta(headings=[]))) is None
assert cp.extract_section(FakeChunk(FakeMeta())) is None
print("extract_section assertions passed.")

# --- chunk_to_dict ---
chunk = FakeChunk(FakeMeta(doc_items=[FakeDocItem([FakeProv(3)])], headings=["Abstract"]))
result = cp.chunk_to_dict(chunk, FakeChunker(), "test-paper-key")
assert result == {
    "source": "test-paper-key",
    "text": "fake contextualized text",
    "section": "Abstract",
    "printed_page": "3",
}
print("chunk_to_dict assertions passed.")

# --- main(): missing docling produces a clean error, not a crash ---
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / "some-paper.pdf").write_bytes(b"fake")
    original_pdf_dir, original_chunks_dir = cp.PAPER_PDF_DIR, cp.PAPERS_CHUNKS_DIR
    cp.PAPER_PDF_DIR = tmp_path
    cp.PAPERS_CHUNKS_DIR = tmp_path / "chunks"
    try:
        cp.main(force=False)  # must not raise, even though docling isn't installed in this test env
    finally:
        cp.PAPER_PDF_DIR, cp.PAPERS_CHUNKS_DIR = original_pdf_dir, original_chunks_dir
print("main() missing-docling-dependency assertions passed (no crash).")

# --- main(): full mocked flow -- success/failure isolation, skip-cache, --force ---
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / "paper-a.pdf").write_bytes(b"fake pdf content for paper A")
    (tmp_path / "paper-b.pdf").write_bytes(b"fake pdf content for paper B")
    chunks_dir = tmp_path / "chunks"

    original_pdf_dir, original_chunks_dir = cp.PAPER_PDF_DIR, cp.PAPERS_CHUNKS_DIR
    original_chunk_paper_pdf, original_build_chunker = cp.chunk_paper_pdf, cp.build_chunker
    cp.PAPER_PDF_DIR = tmp_path
    cp.PAPERS_CHUNKS_DIR = chunks_dir
    cp.build_chunker = lambda *a, **kw: object()

    call_count = {"n": 0}

    def fake_chunk_paper_pdf(pdf_path, source_key, chunker=None):
        call_count["n"] += 1
        if source_key == "paper-b":
            raise RuntimeError("simulated failure")
        return [{"source": source_key, "text": "chunk text", "section": "Intro", "printed_page": "1"}]

    cp.chunk_paper_pdf = fake_chunk_paper_pdf

    try:
        cp.main(force=False)
        assert (chunks_dir / "paper-a.jsonl").exists()
        assert not (chunks_dir / "paper-b.jsonl").exists(), "a failed paper must not produce an output file"

        call_count["n"] = 0
        cp.main(force=False)
        assert call_count["n"] == 1, "only the previously-failed paper should be retried, the successful one should be skipped"

        call_count["n"] = 0
        cp.main(force=True)
        assert call_count["n"] == 2, "--force should reprocess both regardless of cache state"
    finally:
        cp.PAPER_PDF_DIR, cp.PAPERS_CHUNKS_DIR = original_pdf_dir, original_chunks_dir
        cp.chunk_paper_pdf, cp.build_chunker = original_chunk_paper_pdf, original_build_chunker

print("main() full-flow assertions passed (failure isolation, skip-cache, --force).")
print("\nAll chunk_papers assertions passed.")