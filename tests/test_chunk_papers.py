import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from app.ingestion import chunk_papers as cp


def make_pdf(path: Path, text: str):
    """Write a minimal one-page PDF whose text layer holds `text` (ASCII
    only, no parens/backslashes). Small enough to build by hand without a
    PDF library -- the point is to exercise the real pypdf extraction path,
    not to test PDF rendering."""
    stream = f"BT /F1 14 Tf 72 720 Td ({text}) Tj ET"
    objs = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n{stream}\nendstream\nendobj\n",
    ]
    pdf = "%PDF-1.4\n"
    offsets = []
    for obj in objs:
        offsets.append(len(pdf))
        pdf += obj
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    path.write_bytes(pdf.encode("latin-1"))


# --- chunk_paper_pdf: real pypdf extraction, reshaped into the chunk contract ---
with tempfile.TemporaryDirectory() as tmp:
    pdf = Path(tmp) / "paper.pdf"
    make_pdf(pdf, "agentic architectures in south african software teams")
    chunks = cp.chunk_paper_pdf(pdf, "paper-key")

    assert chunks, "a PDF with text must produce at least one chunk"
    assert chunks[0]["source"] == "paper-key"
    assert chunks[0]["section"] is None, "pypdf path has no heading hierarchy -- section stays None"
    assert chunks[0]["chunk_id"] == "paper-key::0"
    assert chunks[0]["printed_page"], "printed_page must be populated"
    assert "agentic" in chunks[0]["text"]
    assert set(chunks[0]) == {"chunk_id", "source", "text", "section", "printed_page"}
print("chunk_paper_pdf assertions passed.")


# --- main(): full mocked flow -- failure isolation, skip-cache, --force ---
with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / "paper-a.pdf").write_bytes(b"fake pdf content for paper A")
    (tmp_path / "paper-b.pdf").write_bytes(b"fake pdf content for paper B")
    chunks_dir = tmp_path / "chunks"

    original_pdf_dir, original_chunks_dir = cp.PAPER_PDF_DIR, cp.PAPERS_CHUNKS_DIR
    original_chunk_paper_pdf = cp.chunk_paper_pdf
    cp.PAPER_PDF_DIR = tmp_path
    cp.PAPERS_CHUNKS_DIR = chunks_dir

    call_count = {"n": 0}

    def fake_chunk_paper_pdf(pdf_path, source_key, encoder=None):
        call_count["n"] += 1
        if source_key == "paper-b":
            raise RuntimeError("simulated failure")
        return [{"source": source_key, "text": "chunk text", "section": None, "printed_page": "1"}]

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
        cp.chunk_paper_pdf = original_chunk_paper_pdf

print("main() full-flow assertions passed (failure isolation, skip-cache, --force).")
print("\nAll chunk_papers assertions passed.")
