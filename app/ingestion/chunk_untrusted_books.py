"""
Extraction + chunking for untrusted books (no real embedded /PageLabels
metadata, per data/report.csv -- e.g. ebook-native PDFs with no printed
page numbers anywhere on the page). Detects chapter/section headings
from font size instead, and cites by chapter + an approximate physical
PDF page rather than a real page number.

Heading detection is calibrated per book, not hardcoded to one book's
font sizes: samples sizes across the book to find the body-text size
(the most common one, since body text dominates any real page), then
treats a line whose average size is notably larger than that as a
heading. This is a heuristic stand-in for Docling's real layout-model
heading detection -- less precise, but doesn't need network access, and
is honest about that via the "approximate" framing already built into
the citation system (see app/retrieval/citations.py).

Shares its skip-cache with chunk_trusted_books.py via chunk_cache.py, so
both pipelines agree on what "unchanged" means.

Usage:
    python -m app.ingestion.chunk_untrusted_books
    python -m app.ingestion.chunk_untrusted_books --force
"""

import json
import bisect
from collections import Counter

import pandas as pd
import pdfplumber
import tiktoken

from app.config import REPORT_PATH, PDF_DIR, CHUNKS_DIR, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS
from app.ingestion.chunk_cache import file_sha256, load_manifest, save_manifest, is_unchanged, update_manifest
from app.ingestion.chunk_trusted_books import sanitize_text

ENCODING_NAME = "cl100k_base"
HEADING_SIZE_RATIO = 1.10  # a line's avg font size must be >= body_size * this to count as a heading
MIN_HEADING_LEN = 2
MAX_HEADING_LEN = 120  # longer than this is almost certainly a misdetected paragraph, not a heading

assert CHUNK_OVERLAP_TOKENS < CHUNK_SIZE_TOKENS, "overlap must be smaller than chunk size"


def group_lines(chars: list, y_tol: float = 2.5) -> list:
    """Groups characters into lines by approximate vertical position,
    returning (text, avg_font_size) per line."""
    chars = sorted(chars, key=lambda c: (round(c["top"] / y_tol), c["x0"]))
    lines, current, current_top = [], [], None

    for ch in chars:
        if current_top is None or abs(ch["top"] - current_top) > y_tol:
            if current:
                lines.append(current)
            current, current_top = [ch], ch["top"]
        else:
            current.append(ch)
    if current:
        lines.append(current)

    result = []
    for line in lines:
        text = "".join(c["text"] for c in line).strip()
        if text:
            avg_size = sum(c["size"] for c in line) / len(line)
            result.append((text, avg_size))
    return result


def find_body_text_size(pdf, sample_every: int = 5, max_samples: int = 60) -> float:
    """Surveys font sizes across a sample of pages to find the body-text
    size -- the most common size weighted by character count, since body
    text dominates any real page far more than headings do."""
    sizes = Counter()
    sampled = 0
    for i, page in enumerate(pdf.pages):
        if i % sample_every != 0:
            continue
        for ch in page.chars:
            sizes[round(ch["size"], 1)] += 1
        sampled += 1
        if sampled >= max_samples:
            break

    if not sizes:
        return 12.0  # fallback for a book with no extractable font-size data at all
    return sizes.most_common(1)[0][0]


def extract_pages_with_headings(pdf, body_size: float) -> list:
    """Same page/byte-offset shape as chunk_trusted_books.extract_pages,
    plus 'heading_at_start': the most recent detected heading as of the
    top of that page."""
    threshold = body_size * HEADING_SIZE_RATIO
    pages = []
    running_offset = 0
    current_heading = None

    for i, page in enumerate(pdf.pages):
        heading_at_start = current_heading

        for text, size in group_lines(page.chars):
            if size >= threshold and MIN_HEADING_LEN <= len(text) <= MAX_HEADING_LEN:
                current_heading = text

        text = (page.extract_text() or "").strip()
        text = sanitize_text(text)
        text_bytes = text.encode("utf-8")
        start = running_offset
        end = start + len(text_bytes)
        pages.append({
            "page_index": i,
            "text": text,
            "start_byte": start,
            "end_byte": end,
            "heading_at_start": heading_at_start,
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

            chunks.append({
                "text": chunk_text,
                "physical_page_start": first_page_idx,
                "physical_page_end": last_page_idx,
                "physical_page_approx": first_page_idx,
                "chapter": pages[first_page_idx]["heading_at_start"],
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
    untrusted = df[df["trust_page_numbers"] == False]

    if untrusted.empty:
        print("No untrusted books found in the report -- nothing to chunk here.")
        return

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    encoder = tiktoken.get_encoding(ENCODING_NAME)
    manifest = load_manifest()

    processed = 0
    skipped = 0

    for _, row in untrusted.iterrows():
        file_name = row["file_name"]
        pdf_path = PDF_DIR / file_name
        if not pdf_path.exists():
            print(f"  [skip] {file_name}: file not found in {PDF_DIR}")
            continue

        book_title = pdf_path.stem
        out_path = CHUNKS_DIR / f"{book_title}.jsonl"
        current_hash = file_sha256(pdf_path)
        settings = {
            "chunk_size_tokens": CHUNK_SIZE_TOKENS,
            "chunk_overlap_tokens": CHUNK_OVERLAP_TOKENS,
            "heading_size_ratio": HEADING_SIZE_RATIO,
        }

        if is_unchanged(manifest, book_title, current_hash, settings, out_path) and not force:
            print(f"  [unchanged] {file_name}: skipping (same file, same chunk settings)")
            skipped += 1
            continue

        print(f"Processing {file_name} (no real page numbers -- using chapter/heading detection) ...")
        with pdfplumber.open(str(pdf_path)) as pdf:
            body_size = find_body_text_size(pdf)
            pages = extract_pages_with_headings(pdf, body_size)

        headings_found = sum(1 for p in pages if p["heading_at_start"])
        if headings_found == 0:
            print(f"  [warning] no headings detected in {file_name} -- every chunk will "
                  f"cite with chapter=None. Body text estimated at {body_size}pt; this "
                  f"book's heading/body font sizes may not differ enough for this "
                  f"heuristic, or it may need a different HEADING_SIZE_RATIO.")

        chunks = chunk_book(pages, encoder=encoder)

        with open(out_path, "w", encoding="utf-8") as f:
            for idx, chunk in enumerate(chunks):
                record = {"chunk_id": f"{book_title}::{idx}", "source": book_title, **chunk}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        update_manifest(manifest, book_title, current_hash, settings)
        processed += 1
        print(f"  -> {len(chunks)} chunks written to {out_path} (body text detected at {body_size}pt)")

    save_manifest(manifest)
    print(f"\nDone. {processed} book(s) (re)chunked, {skipped} unchanged and skipped.")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
