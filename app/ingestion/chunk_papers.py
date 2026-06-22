"""
Converts each paper PDF into a DoclingDocument -- real layout-aware
parsing (headings, tables, reading order via trained layout models),
not a font-size heuristic the way chunk_untrusted_books.py works for
books -- then chunks it with Docling's own HybridChunker rather than a
hand-rolled sliding window. HybridChunker is structure-aware (won't
split a table or a paragraph mid-thought) AND token-aware (splits an
oversized section, merges undersized ones that share the same heading),
which is exactly what a book chunker has to build by hand and Docling
already ships for free.

Configured to tokenize with the project's own cl100k_base encoding (the
same one OpenAI's embeddings already use), via docling-core's
OpenAITokenizer -- so a paper chunk's token count means the same thing
a book chunk's does, not a different tokenizer's approximation of it.

There's no overlap setting here the way books have CHUNK_OVERLAP_TOKENS:
overlap is a sliding-window concept, and HybridChunker isn't a sliding
window -- it splits/merges along real structural boundaries (headings,
paragraphs, tables) instead. Continuity across chunks comes from
contextualize() prepending each chunk's heading path, not from
duplicating text at the edges.

Requires `docling` and `docling-core[chunking-openai]` -- see the
project README for the exact install commands and the disk-space note
(it pulls a full PyTorch + transformers stack even for CPU-only use).

Usage:
    python -m app.cli chunk-papers
    python -m app.cli chunk-papers --force
"""

import json
from pathlib import Path

import tiktoken

from app.config import PAPER_PDF_DIR, PAPERS_CHUNKS_DIR
from app.ingestion.chunk_cache import file_sha256, load_manifest, save_manifest, is_unchanged, update_manifest
from app.logging_config import get_logger

logger = get_logger(__name__)

PAPER_CHUNK_SIZE_TOKENS = 500  # matches CHUNK_SIZE_TOKENS's default for books -- same budget, same encoding
EMBEDDING_ENCODING = "cl100k_base"  # what text-embedding-3-large actually tokenizes with


def build_chunker(max_tokens: int = PAPER_CHUNK_SIZE_TOKENS):
    """Imports docling lazily, inside the function rather than at module
    level -- so importing this module (e.g. for its testable helpers
    below) doesn't require docling to be installed at all."""
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

    tokenizer = OpenAITokenizer(
        tokenizer=tiktoken.get_encoding(EMBEDDING_ENCODING),
        max_tokens=max_tokens,
    )
    return HybridChunker(tokenizer=tokenizer, merge_peers=True)


def extract_page_no(raw_chunk) -> int | None:
    """Best-effort: the first page number found among any of this
    chunk's source doc_items' provenance info. None if Docling couldn't
    attach one (e.g. a chunk that's pure synthesized heading context
    with no directly-backing page element) -- the same kind of honest
    gap chunk_untrusted_books.py already accepts for books with no real
    page labels at all."""
    for item in getattr(raw_chunk.meta, "doc_items", None) or []:
        for prov in getattr(item, "prov", None) or []:
            page_no = getattr(prov, "page_no", None)
            if page_no is not None:
                return int(page_no)
    return None


def extract_section(raw_chunk) -> str | None:
    """Docling's own heading hierarchy for this chunk (e.g. ["Related
    Work", "Agentic Architectures"] for a chunk under that subsection),
    joined the same way a book chunk's chapter name stands in for
    "where in the document did this come from" -- just with real
    multi-level structure instead of one heading string."""
    headings = getattr(raw_chunk.meta, "headings", None) or []
    return " > ".join(headings) if headings else None


def chunk_to_dict(raw_chunk, chunker, source_key: str) -> dict:
    """Converts one Docling DocChunk into this project's existing chunk
    shape (source/text/printed_page) plus "section" instead of
    "chapter" -- embed_upload.py already expects source/text/locator-ish
    fields per chunk, the same shape chunk_trusted_books.py and
    chunk_untrusted_books.py already produce for books."""
    page_no = extract_page_no(raw_chunk)
    return {
        "source": source_key,
        "text": chunker.contextualize(chunk=raw_chunk),
        "section": extract_section(raw_chunk),
        "printed_page": str(page_no) if page_no is not None else None,
    }


def chunk_paper_pdf(pdf_path: Path, source_key: str, chunker=None) -> list[dict]:
    """The one function in this file that actually calls Docling.
    Deliberately thin -- conversion + chunking, then chunk_to_dict() for
    every chunk -- so the parts worth testing (page/section extraction,
    output shape) live in plain functions that don't need Docling
    installed or its layout models downloaded to verify."""
    from docling.document_converter import DocumentConverter

    chunker = chunker or build_chunker()
    result = DocumentConverter().convert(str(pdf_path))
    chunks = [chunk_to_dict(raw_chunk, chunker, source_key) for raw_chunk in chunker.chunk(dl_doc=result.document)]
    # chunk_id matches the books pipeline's exact f"{source_key}::{idx}"
    # convention -- embed_upload_papers.py derives a stable Qdrant point
    # ID from this, the same way embed_upload.py does for books.
    for idx, chunk in enumerate(chunks):
        chunk["chunk_id"] = f"{source_key}::{idx}"
    return chunks


def main(force: bool = False):
    if not PAPER_PDF_DIR.exists():
        logger.warning("%s does not exist -- nothing to chunk", PAPER_PDF_DIR)
        return

    pdf_files = sorted(PAPER_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", PAPER_PDF_DIR)
        return

    try:
        chunker = build_chunker()
    except ImportError:
        logger.error(
            "docling isn't installed -- run `uv add docling` and "
            "`uv add \"docling-core[chunking-openai]\"` first. Expect a "
            "large download (pulls a full PyTorch stack even for "
            "CPU-only use) -- budget several GB of free disk space."
        )
        return

    PAPERS_CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(chunks_dir=PAPERS_CHUNKS_DIR)
    settings = {"max_tokens": PAPER_CHUNK_SIZE_TOKENS, "encoding": EMBEDDING_ENCODING}

    for pdf_path in pdf_files:
        source_key = pdf_path.stem
        out_path = PAPERS_CHUNKS_DIR / f"{source_key}.jsonl"
        current_hash = file_sha256(pdf_path)

        if not force and is_unchanged(manifest, source_key, current_hash, settings, out_path):
            logger.info("[skip] %s: unchanged since last run", source_key)
            continue

        logger.info("[chunking] %s ...", source_key)
        try:
            chunks = chunk_paper_pdf(pdf_path, source_key, chunker=chunker)
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