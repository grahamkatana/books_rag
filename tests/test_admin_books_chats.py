import sys
sys.path.insert(0, ".")

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.models.chat import Chat, Message
from app.auth.security import hash_password

ADMIN_EMAIL, ADMIN_PASSWORD = "admin_books_chats_test@example.com", "adminpass123"
PLAIN_EMAIL, PLAIN_PASSWORD = "plain_books_chats_test@example.com", "plainpass123"
BOOK_KEY = "admin_books_chats_test_book"

with get_session() as session:
    for email, password, is_admin in [(ADMIN_EMAIL, ADMIN_PASSWORD, True), (PLAIN_EMAIL, PLAIN_PASSWORD, False)]:
        if session.query(User).filter_by(email=email).one_or_none() is None:
            session.add(User(email=email, password_hash=hash_password(password), is_admin=is_admin))

    if session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none() is None:
        session.add(Book(source_key=BOOK_KEY, title="Test Book", authors="Author, A.", year=2020,
                          bibliography_verified=False, bibliography_source="filename_guess"))

with get_session() as session:
    plain_user = session.query(User).filter_by(email=PLAIN_EMAIL).one()
    chat = Chat(title="Plain user's chat", user_id=plain_user.id)
    session.add(chat)
    session.flush()
    session.add(Message(chat_id=chat.id, role="user", content="test message"))

app = create_app()
client = app.test_client()


def login(email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["access_token"]


admin_headers = {"Authorization": f"Bearer {login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}
plain_headers = {"Authorization": f"Bearer {login(PLAIN_EMAIL, PLAIN_PASSWORD)}"}

print("--- admin/books: non-admin gets 403 ---")
assert client.get("/api/v1/admin/books/", headers=plain_headers).status_code == 403

print("--- admin/books: admin can list ---")
r = client.get("/api/v1/admin/books/", headers=admin_headers)
assert r.status_code == 200
book_id = [b for b in r.get_json() if b["source_key"] == BOOK_KEY][0]["id"]

print("--- admin/books: update auto-verifies and tags source as manual ---")
r = client.put(f"/api/v1/admin/books/{book_id}", json={"authors": "Corrected, A.", "year": 2021}, headers=admin_headers)
assert r.status_code == 200
body = r.get_json()
assert body["authors"] == "Corrected, A."
assert body["year"] == 2021
assert body["bibliography_verified"] is True
assert body["bibliography_source"] == "manual"

print("--- admin/books: source_key and page_mode are NOT editable through this endpoint ---")
r = client.put(f"/api/v1/admin/books/{book_id}", json={"source_key": "hijacked"}, headers=admin_headers)
assert r.status_code == 422, "an unrecognized field should be rejected by the schema, not silently applied"

print("--- admin/chats: non-admin gets 403, even though one of the chats listed is genuinely theirs ---")
assert client.get("/api/v1/admin/chats/", headers=plain_headers).status_code == 403

print("--- admin/chats: admin sees the plain user's chat with their email attached ---")
r = client.get("/api/v1/admin/chats/", headers=admin_headers)
assert r.status_code == 200
matches = [c for c in r.get_json() if c["title"] == "Plain user's chat"]
assert len(matches) == 1
assert matches[0]["user_email"] == PLAIN_EMAIL
chat_id = matches[0]["id"]

print("--- admin/chats: detail view includes the real message content ---")
r = client.get(f"/api/v1/admin/chats/{chat_id}", headers=admin_headers)
assert r.status_code == 200
assert r.get_json()["messages"][0]["content"] == "test message"

print("--- admin/chats: admin can delete any user's chat ---")
assert client.delete(f"/api/v1/admin/chats/{chat_id}", headers=admin_headers).status_code == 204
assert client.get(f"/api/v1/admin/chats/{chat_id}", headers=admin_headers).status_code == 404

print("\nAll admin books/chats endpoint assertions passed.")

with get_session() as session:
    book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if book is not None:
        session.delete(book)