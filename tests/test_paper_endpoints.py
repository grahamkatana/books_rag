import sys
sys.path.insert(0, ".")

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.models.paper import Paper
from app.models.chat import Chat, Message, Citation
from app.auth.security import hash_password

EMAIL = "test_papers_endpoints@example.com"
PAPER_KEY = "test_papers_endpoints_paper"

with get_session() as session:
    existing_user = session.query(User).filter_by(email=EMAIL).one_or_none()
    if existing_user is not None:
        session.delete(existing_user)
    existing_paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if existing_paper is not None:
        session.delete(existing_paper)

with get_session() as session:
    admin = User(email=EMAIL, password_hash=hash_password("testpass123"), is_admin=True)
    session.add(admin)
    paper = Paper(source_key=PAPER_KEY, title="A Test Paper", authors="Author, A.", year=2026,
                  venue="ICSE 2026", doi="10.1145/test-endpoints",
                  bibliography_verified=True, bibliography_source="manual")
    session.add(paper)
    session.flush()
    chat = Chat(title="Test chat", user_id=admin.id)
    session.add(chat)
    session.flush()
    msg = Message(chat_id=chat.id, role="assistant", content="An answer citing a paper.")
    session.add(msg)
    session.flush()
    session.add(Citation(message_id=msg.id, paper_id=paper.id, apa_text="(Author, 2026, p. 3)", order_index=0))
    chat_id = chat.id
    paper_id = paper.id

app = create_app()
client = app.test_client()

r = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "testpass123"})
assert r.status_code == 200, r.get_json()
token = r.get_json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("--- GET /api/v1/papers/ ---")
r = client.get("/api/v1/papers/", headers=headers)
assert r.status_code == 200
matches = [p for p in r.get_json() if p["source_key"] == PAPER_KEY]
assert len(matches) == 1
assert matches[0]["title"] == "A Test Paper"
print("OK")

print("\n--- GET /api/v1/papers/<id> ---")
r = client.get(f"/api/v1/papers/{paper_id}", headers=headers)
assert r.status_code == 200
assert r.get_json()["doi"] == "10.1145/test-endpoints"
print("OK")

print("\n--- GET /api/v1/admin/papers/ ---")
r = client.get("/api/v1/admin/papers/", headers=headers)
assert r.status_code == 200
admin_matches = [p for p in r.get_json() if p["source_key"] == PAPER_KEY]
assert admin_matches[0]["bibliography_source"] == "manual"
print("OK")

print("\n--- PUT /api/v1/admin/papers/<id> updates and auto-verifies ---")
r = client.put(f"/api/v1/admin/papers/{paper_id}", json={"venue": "Updated Venue"}, headers=headers)
assert r.status_code == 200
assert r.get_json()["venue"] == "Updated Venue"
print("OK")

print("\n--- /api/v1/admin/papers/<id> source_key is not editable ---")
r = client.put(f"/api/v1/admin/papers/{paper_id}", json={"source_key": "hijacked"}, headers=headers)
assert r.status_code == 422, "source_key should be rejected by the schema, not silently applied"
print("OK")

print("\n--- GET /api/v1/chats/<id>: paper_id must appear on the citation ---")
r = client.get(f"/api/v1/chats/{chat_id}", headers=headers)
assert r.status_code == 200
citation = r.get_json()["messages"][0]["citations"][0]
assert citation["paper_id"] == paper_id
assert citation["book_id"] is None
print("OK")

with get_session() as session:
    chat = session.query(Chat).filter_by(title="Test chat").one_or_none()
    if chat is not None:
        session.delete(chat)
    paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if paper is not None:
        session.delete(paper)
    user = session.query(User).filter_by(email=EMAIL).one_or_none()
    if user is not None:
        session.delete(user)

print("\nAll papers-endpoint assertions passed.")