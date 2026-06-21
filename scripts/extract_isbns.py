"""
Scans every PDF in pdfs/books/ for ISBNs and writes file_name -> ISBN(s)
to a CSV. Read-only: doesn't touch report.csv, the database, or anything
else in the ingestion pipeline -- this is a standalone lookup tool, e.g.
for cross-referencing against Open Library/Google Books by hand, or as
a sanity check on what lookup-bibliography or seed-books guessed.

By default only scans a window of pages (the first N + last M) rather
than every page, since an ISBN is almost always on the copyright page
near the front, occasionally on a colophon near the back, and virtually
never in the middle of a 600-page book -- scanning everything would just
be slower for no real gain. Pass --full to scan every page anyway if you
have a reason to.

A regex alone isn't enough to trust a match -- plenty of 10-13 digit
runs in a book aren't ISBNs (page ranges, phone numbers, random
figures). Every candidate is verified against the real ISBN-10/ISBN-13
checksum algorithm before being accepted; only checksum-valid matches
ever make it into the output.

Usage:
    uv run python scripts/extract_isbns.py
    uv run python scripts/extract_isbns.py --output data/isbns.csv
    uv run python scripts/extract_isbns.py --front 40 --back 15
    uv run python scripts/extract_isbns.py --full
"""

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pypdf import PdfReader

from app.config import PDF_DIR, DATA_DIR
from app.logging_config import setup_logging, get_logger

logger = get_logger(__name__)

# Matches "ISBN", "ISBN-10", "ISBN 13", etc., optionally followed by ":"
# and then a run of digits/hyphens/spaces ending in a digit or "X".
# Deliberately permissive -- checksum validation is what actually
# decides if a match is real, not this regex.
ISBN_LABELED_RE = re.compile(
    r"ISBN(?:-?1[03])?\s*:?\s*((?:[0-9][\-\s]?){9,13}[0-9Xx])",
    re.IGNORECASE,
)
# Fallback for text where "ISBN" isn't printed right next to it -- a
# bare run starting with the ISBN-13 prefix. Allows a separator between
# every digit, including inside the "978"/"979" prefix itself: real
# barcode human-readable text is commonly grouped as "9 780306 406157"
# (the leading digit split off by itself), not "978" as one contiguous
# chunk -- a tighter pattern silently missed exactly that real case.
BARE_ISBN13_RE = re.compile(r"\b(9[\-\s]?7[\-\s]?[89][\-\s]?(?:[0-9][\-\s]?){9}[0-9])\b")


def clean_candidate(raw: str) -> str:
    return re.sub(r"[\-\s]", "", raw).upper()


def is_valid_isbn10(candidate: str) -> bool:
    if len(candidate) != 10 or not candidate[:9].isdigit() or candidate[9] not in "0123456789X":
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(candidate))
    return total % 11 == 0


def is_valid_isbn13(candidate: str) -> bool:
    if len(candidate) != 13 or not candidate.isdigit():
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(candidate))
    return total % 10 == 0


def find_isbns_in_text(text: str) -> set:
    found = set()
    for match in ISBN_LABELED_RE.finditer(text):
        candidate = clean_candidate(match.group(1))
        if is_valid_isbn10(candidate) or is_valid_isbn13(candidate):
            found.add(candidate)
    for match in BARE_ISBN13_RE.finditer(text):
        candidate = clean_candidate(match.group(1))
        if is_valid_isbn13(candidate):
            found.add(candidate)
    return found


def pages_to_scan(num_pages: int, front: int, back: int, full: bool) -> list:
    if full:
        return list(range(num_pages))
    front_set = set(range(0, min(front, num_pages)))
    back_set = set(range(max(0, num_pages - back), num_pages))
    return sorted(front_set | back_set)


def process_pdf(pdf_path: Path, front: int, back: int, full: bool) -> dict:
    try:
        reader = PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        indices = pages_to_scan(num_pages, front, back, full)

        found = set()
        for i in indices:
            text = reader.pages[i].extract_text() or ""
            found |= find_isbns_in_text(text)

        isbn_13s = sorted(c for c in found if len(c) == 13)
        isbn_10s = sorted(c for c in found if len(c) == 10)

        if found:
            logger.info("found %d ISBN(s) in %s: %s", len(found), pdf_path.name, sorted(found))
        else:
            logger.warning("no ISBN found in %s (scanned %d of %d pages)",
                            pdf_path.name, len(indices), num_pages)

        return {
            "file_name": pdf_path.name,
            "isbn_13": isbn_13s[0] if isbn_13s else "",
            "isbn_10": isbn_10s[0] if isbn_10s else "",
            "all_isbns_found": "; ".join(sorted(found)),
            "pages_scanned": len(indices),
            "error": "",
        }
    except Exception as e:
        logger.error("Failed to process %s: %s", pdf_path.name, e)
        return {
            "file_name": pdf_path.name,
            "isbn_13": "", "isbn_10": "", "all_isbns_found": "", "pages_scanned": 0,
            "error": str(e),
        }


def main(output_path: Path, front: int, back: int, full: bool):
    setup_logging()

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", PDF_DIR)
        return

    rows = [process_pdf(p, front, back, full) for p in pdf_files]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["file_name", "isbn_13", "isbn_10", "all_isbns_found", "pages_scanned", "error"]
        )
        writer.writeheader()
        writer.writerows(rows)

    found_count = sum(1 for r in rows if r["all_isbns_found"])
    logger.info("Wrote %d row(s) to %s (%d/%d files had at least one ISBN)",
                len(rows), output_path, found_count, len(rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract ISBNs from every PDF in pdfs/books/.")
    parser.add_argument("--output", type=Path, default=DATA_DIR / "isbns.csv")
    parser.add_argument("--front", type=int, default=30, help="How many pages from the start to scan")
    parser.add_argument("--back", type=int, default=10, help="How many pages from the end to scan")
    parser.add_argument("--full", action="store_true", help="Scan every page instead of just front/back")
    args = parser.parse_args()
    main(args.output, args.front, args.back, args.full)