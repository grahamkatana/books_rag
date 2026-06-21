import sys, csv, os
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.book import Book
from app.retrieval.query_engine import build_context_and_lookup, _load_isbn_lookup, ISBN_CSV_PATH

BOOK_KEY = "test_isbn_context_book"


class FakeHit:
    def __init__(self, payload):
        self.payload = payload


with get_session() as session:
    existing = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)

with get_session() as session:
    session.add(Book(source_key=BOOK_KEY, title="Test Book", authors="Author, A.", year=2020,
                      bibliography_verified=True, bibliography_source="manual", page_mode="labeled"))

hits = [FakeHit({"source": BOOK_KEY, "text": "Some excerpt text.", "printed_page": "12"})]
csv_backup = ISBN_CSV_PATH.read_text() if ISBN_CSV_PATH.exists() else None

try:
    # --- no isbns.csv at all: must not crash, must not mention ISBN ---
    if ISBN_CSV_PATH.exists():
        ISBN_CSV_PATH.unlink()

    assert _load_isbn_lookup() == {}

    with get_session() as session:
        context, _ = build_context_and_lookup(session, hits)
    assert "ISBN" not in context, "no isbns.csv should produce no ISBN mention at all"
    assert "<CITATION>(Author, 2020, p. 12)</CITATION>" in context

    # --- isbns.csv present with a real entry for this book ---
    with open(ISBN_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file_name", "isbn_13", "isbn_10", "all_isbns_found", "pages_scanned", "error"])
        writer.writeheader()
        writer.writerow({"file_name": f"{BOOK_KEY}.pdf", "isbn_13": "9780306406157", "isbn_10": "",
                          "all_isbns_found": "9780306406157", "pages_scanned": 30, "error": ""})

    assert _load_isbn_lookup() == {f"{BOOK_KEY}.pdf": "9780306406157"}

    with get_session() as session:
        context, _ = build_context_and_lookup(session, hits)
    assert "ISBN 9780306406157" in context
    assert "never include an isbn" in context.lower()
    # the actual excerpt + citation tag must still be present and unchanged
    assert "<CITATION>(Author, 2020, p. 12)</CITATION>" in context
    assert "Some excerpt text." in context

    # --- a book with no ISBN entry in the CSV: footer should only
    # mention books that actually have one, not blanket-apply ---
    other_hits = [FakeHit({"source": "some-other-book-not-in-csv", "text": "other text", "printed_page": "5"})]
    with get_session() as session:
        existing = session.query(Book).filter_by(source_key="some-other-book-not-in-csv").one_or_none()
        if existing is None:
            session.add(Book(source_key="some-other-book-not-in-csv", title="Other Book",
                              bibliography_verified=False, page_mode="labeled"))
    with get_session() as session:
        context, _ = build_context_and_lookup(session, other_hits)
    assert "ISBN" not in context, "a book absent from isbns.csv should not get an ISBN mention"

    print("All ISBN-context regression assertions passed.")
finally:
    if csv_backup is not None:
        ISBN_CSV_PATH.write_text(csv_backup)
    elif ISBN_CSV_PATH.exists():
        ISBN_CSV_PATH.unlink()
    with get_session() as session:
        for key in (BOOK_KEY, "some-other-book-not-in-csv"):
            row = session.query(Book).filter_by(source_key=key).one_or_none()
            if row is not None:
                session.delete(row)