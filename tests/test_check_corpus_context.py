import sys
sys.path.insert(0, ".")
sys.path.insert(0, "scripts")

from unittest.mock import patch, MagicMock

from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.corpus_context_check import CorpusContextCheck
import check_corpus_context as ccc

BOOK_KEY = "test_ccc_book"
PAPER_KEY = "test_ccc_paper"

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)
    paper_row = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if paper_row is not None:
        session.delete(paper_row)

print("--- check_source_context: no hits at all -- no LLM call (cost control) ---")
with patch.object(ccc, "embed_query", return_value=[0.1]), \
     patch.object(ccc, "search_chunks", return_value=[]):
    fake_client = MagicMock()
    known, explanation = ccc.check_source_context(fake_client, MagicMock(), "src", "books", "Title")
assert known is False
assert "No chunks at all" in explanation
assert not fake_client.chat.completions.create.called
print("OK")

print("\n--- check_source_context: real content judged context_known=True ---")
hit = MagicMock()
hit.payload = {"text": "This book is a comprehensive guide to software engineering."}
fake_client2 = MagicMock()
fake_response = MagicMock()
fake_response.choices = [MagicMock(message=MagicMock(
    content='{"context_known": true, "explanation": "Clearly about software engineering."}'
))]
fake_client2.chat.completions.create.return_value = fake_response
with patch.object(ccc, "embed_query", return_value=[0.1]), \
     patch.object(ccc, "search_chunks", return_value=[hit]):
    known2, explanation2 = ccc.check_source_context(fake_client2, MagicMock(), "src", "books", "Title")
assert known2 is True
assert explanation2 == "Clearly about software engineering."
print("OK")

print("\n--- check_source_context: retrieval raises, LLM returns malformed JSON -- neither crashes ---")
with patch.object(ccc, "embed_query", side_effect=RuntimeError("boom")):
    known3, explanation3 = ccc.check_source_context(MagicMock(), MagicMock(), "src", "books", "Title")
assert known3 is False and "Retrieval itself failed" in explanation3

hit4 = MagicMock()
hit4.payload = {"text": "Some text."}
fake_client4 = MagicMock()
fake_response4 = MagicMock()
fake_response4.choices = [MagicMock(message=MagicMock(content="not json"))]
fake_client4.chat.completions.create.return_value = fake_response4
with patch.object(ccc, "embed_query", return_value=[0.1]), \
     patch.object(ccc, "search_chunks", return_value=[hit4]):
    known4, explanation4 = ccc.check_source_context(fake_client4, MagicMock(), "src", "books", "Title")
assert known4 is False and "Could not get or parse" in explanation4
print("OK")

print("\n--- record_check: upserts, never duplicates, auto-(un)flags ---")
with get_session() as session:
    book = Book(source_key=BOOK_KEY, title="Test Book", bibliography_verified=True, page_mode="labeled")
    session.add(book)
    session.flush()
    book_id = book.id

ccc.record_check(book_id=book_id, paper_id=None, context_known=False, explanation="Garbled.")
with get_session() as session:
    check = session.query(CorpusContextCheck).filter_by(book_id=book_id).one()
    assert check.context_known is False
    assert check.marked_for_delete is True
    first_id = check.id

ccc.record_check(book_id=book_id, paper_id=None, context_known=True, explanation="Fine now.")
with get_session() as session:
    checks = session.query(CorpusContextCheck).filter_by(book_id=book_id).all()
    assert len(checks) == 1, "must update, not duplicate"
    assert checks[0].id == first_id
    assert checks[0].context_known is True
    assert checks[0].marked_for_delete is False
print("OK")

print("\n--- main(): full orchestration across books and papers, --books-only/--papers-only ---")
with get_session() as session:
    paper = Paper(source_key=PAPER_KEY, title="Test Paper")
    session.add(paper)
    session.flush()
    paper_id = paper.id

calls = []


def track_check(openai_client, qdrant, source_key, corpus, title, top_k=5):
    calls.append((corpus, source_key))
    return (False, "bad") if "book" in source_key else (True, "good")


with patch.object(ccc, "get_openai_client", return_value=MagicMock()), \
     patch.object(ccc, "get_qdrant_client", return_value=MagicMock()), \
     patch.object(ccc, "check_source_context", side_effect=track_check):
    ccc.main(check_books=True, check_papers=True)

assert (("books", BOOK_KEY) in calls) and (("papers", PAPER_KEY) in calls)
with get_session() as session:
    book_check = session.query(CorpusContextCheck).filter_by(book_id=book_id).one()
    paper_check = session.query(CorpusContextCheck).filter_by(paper_id=paper_id).one()
    assert book_check.marked_for_delete is True
    assert paper_check.context_known is True and paper_check.marked_for_delete is False
print("OK")

calls.clear()
with patch.object(ccc, "get_openai_client", return_value=MagicMock()), \
     patch.object(ccc, "get_qdrant_client", return_value=MagicMock()), \
     patch.object(ccc, "check_source_context", side_effect=track_check):
    ccc.main(check_books=False, check_papers=True)
assert all(c == "papers" for c, _ in calls), "books-disabled run must never touch books"
print("OK")

with get_session() as session:
    session.delete(session.query(CorpusContextCheck).filter_by(book_id=book_id).one())
    session.delete(session.query(CorpusContextCheck).filter_by(paper_id=paper_id).one())
    session.delete(session.query(Book).filter_by(source_key=BOOK_KEY).one())
    session.delete(session.query(Paper).filter_by(source_key=PAPER_KEY).one())

print("\nAll check_corpus_context assertions passed.")