import sys
sys.path.insert(0, ".")

from unittest.mock import patch

import app.api.clients as clients
from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password

# get_openai_client()/get_qdrant_client() lazily construct real clients on
# first use -- populating the module's singleton slots directly (the same
# pattern test_api.py already uses) means that construction never
# happens at all, rather than needing a real or dummy API key.
clients._openai_client = object()
clients._qdrant_client = object()

EMAIL = "test_ask_corpus_api@example.com"

with get_session() as session:
    existing = session.query(User).filter_by(email=EMAIL).one_or_none()
    if existing is not None:
        session.delete(existing)

with get_session() as session:
    session.add(User(email=EMAIL, password_hash=hash_password("testpass123"), is_admin=False))

app = create_app()
client = app.test_client()

r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "testpass123"})
assert r.status_code == 200, r.get_json()
token = r.get_json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("--- default corpus (field omitted entirely) resolves to 'books' ---")
with patch("app.api.v1.ask.answer_question") as mock_answer:
    mock_answer.return_value = {"chat_id": 1, "answer": "ok", "citations": []}
    r = client.post("/api/v1/ask/", json={"question": "test"}, headers=headers)
    assert r.status_code == 200
    assert mock_answer.call_args.kwargs["corpus"] == "books"
print("OK")

print("\n--- explicit corpus='papers' passes through ---")
with patch("app.api.v1.ask.answer_question") as mock_answer:
    mock_answer.return_value = {"chat_id": 1, "answer": "ok", "citations": []}
    r = client.post("/api/v1/ask/", json={"question": "test", "corpus": "papers"}, headers=headers)
    assert r.status_code == 200
    assert mock_answer.call_args.kwargs["corpus"] == "papers"
print("OK")

print("\n--- explicit corpus='both' passes through ---")
with patch("app.api.v1.ask.answer_question") as mock_answer:
    mock_answer.return_value = {"chat_id": 1, "answer": "ok", "citations": []}
    r = client.post("/api/v1/ask/", json={"question": "test", "corpus": "both"}, headers=headers)
    assert r.status_code == 200
    assert mock_answer.call_args.kwargs["corpus"] == "both"
print("OK")

print("\n--- an invalid corpus value is rejected with 422 and never reaches answer_question ---")
with patch("app.api.v1.ask.answer_question") as mock_answer:
    r = client.post("/api/v1/ask/", json={"question": "test", "corpus": "not-a-real-corpus"}, headers=headers)
    assert r.status_code == 422
    assert not mock_answer.called
print("OK")

with get_session() as session:
    user = session.query(User).filter_by(email=EMAIL).one_or_none()
    if user is not None:
        session.delete(user)

print("\nAll ask-endpoint corpus assertions passed.")