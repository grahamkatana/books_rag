"""
Override Book/Paper bibliography from the verified manifest CSVs produced by
manifest.py (books) and papers_manifest.py (papers) in the Books working folder.

Match by filename stem: the manifest's `file` column (minus extension) equals
the DB `source_key`. Only rows the manifest did NOT flag are touched -- anything
with needs_review set, or a paper with duplicate_of set, is left exactly as the
ingest's auto-lookup left it. Overridden rows get the manifest's
title/authors/year/publisher(/venue/doi/abstract), bibliography_source="manifest",
and bibliography_verified=True.

Run inside the API image against the cluster DB (via port-forward):

    docker run --rm -v "$PWD/app:/app/app" \
      -v "$HOME/Downloads/Books/books-md:/manifests/books-md" \
      -v "$HOME/Downloads/Books/papers-md:/manifests/papers-md" \
      -e DATABASE_URL="postgresql+psycopg://book_rag:...@host.docker.internal:5433/book_rag" \
      --entrypoint /app/.venv/bin/python grahamkatana/books-rag-api:ingest \
      -c "from app.ingestion.override_metadata import main; main()"

Use --dry-run to see counts without writing.
"""

import csv
import os
import sys

from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper

BOOKS_CSV = os.environ.get("BOOKS_MANIFEST", "/manifests/books-md/manifest.csv")
PAPERS_CSV = os.environ.get("PAPERS_MANIFEST", "/manifests/papers-md/papers_manifest.csv")


def _stem(name):
    return name.rsplit(".", 1)[0] if "." in name else name


def _clean(s):
    s = (s or "").strip()
    return s or None


def _int(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _flagged(s):
    """True when the manifest's needs_review / duplicate_of column is set to
    something affirmative (e.g. "yes"). Empty, "no", "false", "0" -> False."""
    v = _clean(s)
    return v is not None and v.lower() not in ("no", "false", "0")


def override_books(session, dry_run):
    if not os.path.exists(BOOKS_CSV):
        print(f"books manifest not found: {BOOKS_CSV}")
        return 0, 0, 0
    updated = skipped = missing = 0
    with open(BOOKS_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        key = _stem(r.get("file", ""))
        book = session.query(Book).filter_by(source_key=key).one_or_none()
        if book is None:
            missing += 1
            continue
        if _flagged(r.get("needs_review")):
            skipped += 1
            continue
        title = _clean(r.get("title"))
        authors = _clean(r.get("authors"))
        year = _int(r.get("year"))
        publisher = _clean(r.get("publisher"))
        if not dry_run:
            if title:
                book.title = title
            book.authors = authors
            book.year = year
            book.publisher = publisher
            book.bibliography_source = "manifest"
            book.bibliography_verified = True
        updated += 1
    return updated, skipped, missing


def override_papers(session, dry_run):
    if not os.path.exists(PAPERS_CSV):
        print(f"papers manifest not found: {PAPERS_CSV}")
        return 0, 0, 0
    updated = skipped = missing = 0
    # DOIs the auto-lookup already wrote; never hand the same one to two rows.
    existing_dois = {d for (d,) in session.query(Paper.doi).filter(Paper.doi.isnot(None))}
    seen_dois = set()
    with open(PAPERS_CSV, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        key = _stem(r.get("file", ""))
        paper = session.query(Paper).filter_by(source_key=key).one_or_none()
        if paper is None:
            missing += 1
            continue
        if _flagged(r.get("needs_review")) or _flagged(r.get("duplicate_of")):
            skipped += 1
            continue
        title = _clean(r.get("title"))
        authors = _clean(r.get("authors"))
        year = _int(r.get("year"))
        venue = _clean(r.get("venue_or_org"))
        doi = _clean(r.get("doi"))
        abstract = _clean(r.get("summary"))
        if not dry_run:
            if title:
                paper.title = title
            paper.authors = authors
            paper.year = year
            paper.venue = venue
            # Paper.doi is unique -- never assign a doi already held by another
            # row (from a prior auto-lookup, or assigned earlier in this run).
            if doi and doi not in existing_dois and doi not in seen_dois:
                paper.doi = doi
                seen_dois.add(doi)
            paper.abstract = abstract
            paper.bibliography_source = "manifest"
            paper.bibliography_verified = True
        updated += 1
    return updated, skipped, missing


def main():
    dry_run = "--dry-run" in sys.argv
    with get_session() as session:
        bu, bs, bm = override_books(session, dry_run)
        pu, ps, pm = override_papers(session, dry_run)
    if dry_run:
        print("[DRY-RUN] nothing committed")
    print(f"books:  {bu} overridden, {bs} needs_review skipped, {bm} no matching DB row")
    print(f"papers: {pu} overridden, {ps} skipped (needs_review/duplicate), {pm} no matching DB row")


if __name__ == "__main__":
    main()
