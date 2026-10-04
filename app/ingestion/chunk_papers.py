"""
Converts each paper PDF into token-sized chunks ready for embedding.

Uses the same pypdf + tiktoken sliding-window path as
chunk_trusted_books.py (extract_pages/chunk_book are imported from there,
not reimplemented). Docling's layout-aware parsing was removed: on a CPU-only
8GB host it took ~20 min/paper and OOM-killed after two papers, which is
unworkable for a corpus of hundreds. Academic PDFs are digital-native with a
real text layer, so pypdf's per-page extract_text() is sufficient; the one
known trade-off is that two-column papers can interleave text at column
boundaries -- titles/abstracts/DOIs (already verified in Postgres) are
unaffected, and retrieval over ~500-token chunks stays sound.

Chunk output shape is unchanged (source/text/section/printed_page/chunk_id),
so embed_upload_papers.py and delete_paper.py need no changes. `section` is
always None now -- pypdf gives no heading hierarchy -- and is kept only to
preserve the payload field the embed step already writes through.

Usage:
    python -m app.cli chunk-papers
    python -m app.cli chunk-papers --force
"""

import json
from pathlib import Path

import tiktoken
from pypdf import PdfReader

from app.config import PAPER_PDF_DIR, PAPERS_CHUNKS_DIR, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS
from app.ingestion.chunk_cache import file_sha256, load_manifest, save_manifest, is_unchanged, update_manifest
from app.ingestion.chunk_trusted_books import extract_pages, chunk_book
from app.logging_config import get_logger

logger = get_logger(__name__)

ENCODING_NAME = "cl100k_base"


def chunk_paper_pdf(pdf_path: Path, source_key: str, encoder=None) -> list[dict]:
    """pypdf text extraction + the books' sliding-window token chunker,
    reshaped into the papers chunk contract (adds source + stable chunk_id,
    drops the book-only physical_page fields, sets section=None)."""
    encoder = encoder or tiktoken.get_encoding(ENCODING_NAME)
    reader = PdfReader(str(pdf_path))
    labels = reader.page_labels
    pages = extract_pages(reader, labels)
    raw_chunks = chunk_book(pages, encoder=encoder)

    chunks = []
    for idx, c in enumerate(raw_chunks):
        chunks.append({
            "chunk_id": f"{source_key}::{idx}",
            "source": source_key,
            "text": c["text"],
            "section": None,
            "printed_page": c["printed_page"],
        })
    return chunks


def main(force: bool = False):
    if not PAPER_PDF_DIR.exists():
        logger.warning("%s does not exist -- nothing to chunk", PAPER_PDF_DIR)
        return

    pdf_files = sorted(PAPER_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", PAPER_PDF_DIR)
        return

    PAPERS_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    encoder = tiktoken.get_encoding(ENCODING_NAME)
    manifest = load_manifest(chunks_dir=PAPERS_CHUNKS_DIR)
    settings = {"chunk_size_tokens": CHUNK_SIZE_TOKENS, "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS}

    for pdf_path in pdf_files:
        source_key = pdf_path.stem
        out_path = PAPERS_CHUNKS_DIR / f"{source_key}.jsonl"
        current_hash = file_sha256(pdf_path)

        if not force and is_unchanged(manifest, source_key, current_hash, settings, out_path):
            logger.info("[skip] %s: unchanged since last run", source_key)
            continue

        logger.info("[chunking] %s ...", source_key)
        try:
            chunks = chunk_paper_pdf(pdf_path, source_key, encoder=encoder)
        except Exception as e:
            logger.error("Failed to chunk %s: %s", source_key, e)
            continue

        with open(out_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        update_manifest(manifest, source_key, current_hash, settings)
        logger.info("[done] %s -> %d chunk(s)", source_key, len(chunks))

    save_manifest(manifest, chunks_dir=PAPERS_CHUNKS_DIR)


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
