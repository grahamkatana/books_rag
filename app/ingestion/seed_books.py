"""
Creates a Book row for any new file in data/report.csv that doesn't have
one yet, using a best-effort guess from the filename as a starting
point. Never touches an existing row -- once a book exists in the
database, this script leaves its bibliography alone regardless of where
that data came from (filename guess, lookup-bibliography, or a manual
edit in /admin). That's the whole point of moving bibliography fully
into the database: there's a single source of truth per book, and
nothing here silently overwrites it.

New rows start with bibliography_verified=False and
bibliography_source="filename_guess" -- run lookup-bibliography next to
improve them via Brave + an LLM, or just fix them directly in /admin.

Usage:
    python -m app.ingestion.seed_books
"""

import re

import pandas as pd

from app.config import REPORT_PATH
from app.db.session import get_session
from app.models.book import Book

EDITION_RE = re.compile(r"(\d+)(?:st|nd|rd|th)?[\s_-]*edition", re.IGNORECASE)
SHORT_EDITION_RE = re.compile(r"\b(\d+)E\b")
NOISE_TOKENS = ["oceanofpdf", "_com_", "ac__id_", "ac_id_"]  # common scan/piracy-site fragments


def clean_words(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("_", " ").replace("-", " ")).strip()


def guess_metadata_from_filename(stem: str) -> dict:
    """Best-effort and deliberately conservative -- this is just a
    starting point for a brand-new row, not a substitute for checking
    the actual copyright page or running lookup-bibliography."""
    lowered = stem.lower()
    looks_noisy = any(tok in lowered for tok in NOISE_TOKENS)

    authors = None
    title_part = stem

    by_match = re.search(r"(.+?)[-_]by[-_](.+)", stem, re.IGNORECASE)
    if by_match:
        title_part = by_match.group(1)
        authors = clean_words(by_match.group(2))
    else:
        trailing_name = re.search(r"^(.*)_-_([A-Z][a-zA-Z]+(?:_[A-Z][a-zA-Z]+)+)$", stem)
        if trailing_name:
            title_part = trailing_name.group(1)
            authors = clean_words(trailing_name.group(2))

    edition = None
    m = EDITION_RE.search(stem)
    if m:
        edition = f"{m.group(1)} ed."
        title_part = EDITION_RE.sub("", title_part)
    else:
        m2 = SHORT_EDITION_RE.search(stem)
        if m2:
            edition = f"{m2.group(1)} ed."
            title_part = SHORT_EDITION_RE.sub("", title_part)

    for tok in ["OceanofPDF_com", "oceanofpdf_com"]:
        title_part = title_part.replace(tok, "")

    title = clean_words(title_part).strip(" -_")

    return {
        "title": title or stem,
        "authors": authors,
        "edition": edition,
        "needs_review": looks_noisy or authors is None,
    }


def resolve_preferred_editions(session) -> None:
    """For every work_key shared by more than one book, automatically
    marks the highest-year edition as preferred and every other edition
    in that group as not preferred -- unless exactly one book in the
    group has edition_pinned=True (set deliberately via /admin, separate
    from bibliography_verified -- see the field's docstring on the Book
    model for why those two needed to stay separate), in which case that
    pin wins and the rest of the group is set around it instead.

    Requiring exactly one match (not "at least one") matters: a zero-pin
    state (normal, before any human's looked at the group) and an
    ambiguous multi-pin state (e.g. two editions both mistakenly marked
    pinned) both fall back to picking the highest year fresh, rather than
    locking in behavior nobody actually intended."""
    books_with_work_key = session.query(Book).filter(Book.work_key.isnot(None)).all()
    groups: dict[str, list[Book]] = {}
    for b in books_with_work_key:
        groups.setdefault(b.work_key, []).append(b)

    for work_key, group in groups.items():
        if len(group) < 2:
            continue  # no other editions to compare against

        pinned = [b for b in group if b.is_preferred_edition and b.edition_pinned]
        if len(pinned) == 1:
            for b in group:
                b.is_preferred_edition = (b is pinned[0])
        else:
            # Zero pins (normal case before anyone's looked at this group)
            # or an ambiguous multiple-pin state (e.g. two editions both
            # got marked verified+preferred by mistake) -- either way,
            # fall back to picking the highest year fresh rather than
            # guessing which pin should win.
            newest = max(group, key=lambda b: (b.year or 0))
            for b in group:
                b.is_preferred_edition = (b is newest)
            print(f"  [edition resolution] work_key={work_key!r}: preferring "
                  f"{newest.source_key!r} (year={newest.year}) over "
                  f"{[b.source_key for b in group if b is not newest]}")
        session.add_all(group)


def main():
    if not REPORT_PATH.exists():
        raise SystemExit(f"{REPORT_PATH} not found -- run the trust report builder first.")

    df = pd.read_csv(REPORT_PATH)
    created = 0

    with get_session() as session:
        for _, row in df.iterrows():
            source_key = row["file_name"].rsplit(".", 1)[0]
            page_mode = "labeled" if bool(row["trust_page_numbers"]) else "approximate"

            existing = session.query(Book).filter_by(source_key=source_key).one_or_none()
            if existing is not None:
                print(f"  [unchanged] {source_key}: already in the database, leaving it alone")
                continue

            guessed = guess_metadata_from_filename(source_key)
            book = Book(
                source_key=source_key,
                title=guessed["title"],
                authors=guessed["authors"],
                edition=guessed["edition"],
                page_mode=page_mode,
                bibliography_verified=False,
                bibliography_source="filename_guess",
            )
            session.add(book)
            created += 1

            flag = "NEEDS REVIEW" if guessed["needs_review"] else "best-effort guess"
            print(f"  [{flag}] {source_key}")
            print(f"      title={book.title!r} authors={book.authors!r} edition={book.edition!r}")

        session.flush()
        resolve_preferred_editions(session)

    print(f"\nDone. {created} new book(s) added. Run lookup-bibliography next "
          f"to improve their bibliography via Brave + an LLM, or fix any "
          f"book directly at /admin.")


if __name__ == "__main__":
    main()
