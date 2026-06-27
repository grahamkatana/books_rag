import sys
sys.path.insert(0, ".")

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.models.paper import Paper
from app.models.corpus_context_check import CorpusContextCheck
from app.auth.security import hash_password

ADMIN_EMAIL = "test_ccc_endpoint_admin@example.com"
PLAIN_EMAIL = "test_ccc_endpoint_plain@example.com"
BOOK_KEY = "test_ccc_endpoint_book"
PAPER_KEY = "test_ccc_endpoint_paper"

with get_session() as session:
    for email in (ADMIN_EMAIL, PLAIN_EMAIL):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)
    book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if book is not None:
        session.delete(book)
    paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if paper is not None:
        session.delete(paper)

with get_session() as session:
    session.add(User(email=ADMIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=True))
    session.add(User(email=PLAIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=False))

    book = Book(source_key=BOOK_KEY, title="Flagged Book", bibliography_verified=True, page_mode="labeled")
    session.add(book)
    session.flush()
    session.add(CorpusContextCheck(book_id=book.id, context_known=False, explanation="Garbled.", marked_for_delete=True))

    paper = Paper(source_key=PAPER_KEY, title="Flagged Paper")
    session.add(paper)
    session.flush()
    session.add(CorpusContextCheck(paper_id=paper.id, context_known=True, explanation="Fine.", marked_for_delete=False))

    # A stale check -- its source is already gone, both FKs are null
    session.add(CorpusContextCheck(book_id=None, paper_id=None, context_known=False, explanation="orphaned", marked_for_delete=True))

app = create_app()
client = app.test_client()
token_admin = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
token_plain = client.post("/api/v1/auth/login", json={"email": PLAIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
h_admin = {"Authorization": f"Bearer {token_admin}"}
h_plain = {"Authorization": f"Bearer {token_plain}"}

print("--- non-admin: 403 ---")
assert client.get("/api/v1/admin/corpus-context-checks/", headers=h_plain).status_code == 403
print("OK")

print("\n--- admin GET list: book+paper resolved correctly, stale check filtered out ---")
r = client.get("/api/v1/admin/corpus-context-checks/", headers=h_admin)
assert r.status_code == 200
body = r.get_json()
assert len(body) == 2, f"stale check must be filtered out, got {len(body)} rows"
by_title = {c["title"]: c for c in body}
assert by_title["Flagged Book"]["item_type"] == "book"
assert by_title["Flagged Book"]["marked_for_delete"] is True
assert by_title["Flagged Paper"]["item_type"] == "paper"
assert by_title["Flagged Paper"]["marked_for_delete"] is False
check_id = by_title["Flagged Paper"]["id"]
print("OK")

print("\n--- admin PUT: toggles marked_for_delete ---")
r = client.put(f"/api/v1/admin/corpus-context-checks/{check_id}", json={"marked_for_delete": True}, headers=h_admin)
assert r.status_code == 200
assert r.get_json()["marked_for_delete"] is True
print("OK")

print("\n--- nonexistent check_id: 404 ---")
assert client.put("/api/v1/admin/corpus-context-checks/999999", json={"marked_for_delete": True}, headers=h_admin).status_code == 404
print("OK")

with get_session() as session:
    for check in session.query(CorpusContextCheck).all():
        session.delete(check)
    book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if book is not None:
        session.delete(book)
    paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if paper is not None:
        session.delete(paper)
    for email in (ADMIN_EMAIL, PLAIN_EMAIL):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)

print("\nAll admin_corpus_context endpoint assertions passed.")