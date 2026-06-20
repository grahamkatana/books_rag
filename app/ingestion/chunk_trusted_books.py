"""
Extraction + chunking for trusted books (those with verified embedded
/PageLabels metadata, per data/report.csv). Token-chunks each book with
tiktoken, allowing chunks to span pages, and writes one
data/chunks/<book>.jsonl per book ready for embedding.

Skips a book entirely if its PDF hasn't changed (by content hash) and the
chunk size/overlap settings haven't changed since the last run -- see
chunk_cache.py, shared with chunk_untrusted_books.py so both pipelines
agree on what "unchanged" means. Pass force=True (or --force on the CLI)
to reprocess everything regardless.

Untrusted books are skipped here -- see chunk_untrusted_books.py for the
chapter/heading based pipeline they need instead.

Usage:
    python -m app.ingestion.chunk_trusted_books
    python -m app.ingestion.chunk_trusted_books --force
"""

import json
import bisect

import pandas as pd
import tiktoken
from pypdf import PdfReader

from app.config import REPORT_PATH, PDF_DIR, CHUNKS_DIR, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS
from app.ingestion.chunk_cache import file_sha256, load_manifest, save_manifest, is_unchanged, update_manifest
from app.logging_config import get_logger

logger = get_logger(__name__)

ENCODING_NAME = "cl100k_base"  # used by text-embedding-3-small/large and ada-002

assert CHUNK_OVERLAP_TOKENS < CHUNK_SIZE_TOKENS, "overlap must be smaller than chunk size"


def sanitize_text(text: str) -> str:
    """Strips lone UTF-16 surrogate codepoints that some PDFs produce from
    broken font/cmap decoding -- most often seen in math-heavy books where
    a symbol (e.g. an italic variable from the Mathematical Alphanumeric
    Symbols block) gets mis-extracted into an unpaired surrogate. These
    aren't valid standalone Unicode and crash UTF-8 encoding later if left
    in; there's no "correct" character to recover, since the source
    extraction was already broken for whatever this represented. Dropping
    silently is more honest than substituting a visible "?" for a
    character we can't actually identify."""
    return text.encode("utf-8", errors="ignore").decode("utf-8")


def extract_pages(reader: PdfReader, labels: list) -> list:
    pages = []
    running_offset = 0
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        text = sanitize_text(text)
        text_bytes = text.encode("utf-8")
        start = running_offset
        end = start + len(text_bytes)
        pages.append({
            "page_index": i,
            "label": labels[i] if i < len(labels) else str(i),
            "text": text,
            "start_byte": start,
            "end_byte": end,
        })
        running_offset = end + 1
    return pages


def page_index_for_byte_offset(pages: list, page_starts: list, byte_pos: int) -> int:
    idx = bisect.bisect_right(page_starts, byte_pos) - 1
    return max(0, min(idx, len(pages) - 1))


def chunk_book(pages: list, encoder=None) -> list:
    if encoder is None:
        encoder = tiktoken.get_encoding(ENCODING_NAME)

    full_text = "\n".join(p["text"] for p in pages)
    full_bytes = full_text.encode("utf-8")
    tokens = encoder.encode(full_text, disallowed_special=())

    cum_offsets = [0] * (len(tokens) + 1)
    running = 0
    for i, t in enumerate(tokens):
        running += len(encoder.decode_single_token_bytes(t))
        cum_offsets[i + 1] = running

    page_starts = [p["start_byte"] for p in pages]

    chunks = []
    i = 0
    n = len(tokens)
    while i < n:
        j = min(i + CHUNK_SIZE_TOKENS, n)
        start_byte = cum_offsets[i]
        end_byte = cum_offsets[j]
        chunk_text = full_bytes[start_byte:end_byte].decode("utf-8", errors="ignore").strip()

        if chunk_text:
            first_page_idx = page_index_for_byte_offset(pages, page_starts, start_byte)
            last_page_idx = page_index_for_byte_offset(pages, page_starts, max(end_byte - 1, start_byte))
            first_label = pages[first_page_idx]["label"]
            last_label = pages[last_page_idx]["label"]
            page_citation = (
                first_label if first_page_idx == last_page_idx
                else f"{first_label}-{last_label}"
            )
            chunks.append({
                "text": chunk_text,
                "physical_page_start": first_page_idx,
                "physical_page_end": last_page_idx,
                "printed_page": page_citation,
                "token_count": j - i,
            })

        if j == n:
            break
        i = j - CHUNK_OVERLAP_TOKENS

    return chunks


def main(force: bool = False):
    if not REPORT_PATH.exists():
        raise SystemExit(f"{REPORT_PATH} not found -- run build_trust_report first.")

    df = pd.read_csv(REPORT_PATH)
    trusted = df[df["trust_page_numbers"] == True]

    if trusted.empty:
        logger.info("No trusted books found in the report -- nothing to chunk.")
        return

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    encoder = tiktoken.get_encoding(ENCODING_NAME)
    manifest = load_manifest()

    processed = 0
    skipped = 0

    for _, row in trusted.iterrows():
        file_name = row["file_name"]
        pdf_path = PDF_DIR / file_name
        if not pdf_path.exists():
            logger.info("  [skip] %s: file not found in %s", file_name, PDF_DIR)
            continue

        book_title = pdf_path.stem
        out_path = CHUNKS_DIR / f"{book_title}.jsonl"
        current_hash = file_sha256(pdf_path)
        settings = {"chunk_size_tokens": CHUNK_SIZE_TOKENS, "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS}

        if is_unchanged(manifest, book_title, current_hash, settings, out_path) and not force:
            logger.info("  [unchanged] %s: skipping (same file, same chunk settings)", file_name)
            skipped += 1
            continue

        logger.info("Processing %s ...", file_name)
        # logger.warning("no headings detected in %s", file_name)
        # logger.error("Brave search failed for %s: %s", book.source_key, e)
        reader = PdfReader(str(pdf_path))
        labels = reader.page_labels

        pages = extract_pages(reader, labels)
        chunks = chunk_book(pages, encoder=encoder)

        with open(out_path, "w", encoding="utf-8") as f:
            for idx, chunk in enumerate(chunks):
                record = {"chunk_id": f"{book_title}::{idx}", "source": book_title, **chunk}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        update_manifest(manifest, book_title, current_hash, settings)
        processed += 1
        logger.info("Processing %s ...", file_name)
        logger.info("  -> %d chunks written to %s", len(chunks), out_path)

    save_manifest(manifest)
    logger.info("\nDone. %d book(s) (re)chunked, %d unchanged and skipped.", processed, skipped)


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
