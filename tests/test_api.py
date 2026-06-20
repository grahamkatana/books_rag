import sys, random, json
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION
import app.api.clients as clients


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector

class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]

class FakeChoiceMessage:
    def __init__(self, content):
        self.content = content

class FakeChoice:
    def __init__(self, content):
        self.message = FakeChoiceMessage(content)

class FakeChatResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeStreamDelta:
    def __init__(self, content):
        self.content = content

class FakeStreamChoice:
    def __init__(self, content):
        self.delta = FakeStreamDelta(content)

class FakeStreamChunk:
    def __init__(self, content):
        self.choices = [FakeStreamChoice(content)]


class FakeOpenAIClient:
    class embeddings:
        @staticmethod
        def create(model, input):
            vectors = [[random.random() for _ in range(EMBEDDING_DIM)] for _ in input]
            return FakeEmbeddingResponse(vectors)

    class chat:
        class completions:
            @staticmethod
            def create(model, messages, stream=False):
                if stream:
                    words = "Agile methods emphasize iterative delivery and customer feedback.".split(" ")
                    return [FakeStreamChunk(w + " ") for w in words]
                return FakeChatResponse("Agile methods emphasize iterative delivery.")


# Seed a fake Qdrant collection
qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
chunk = {"chunk_id": "sommerville::1", "source": "Software-Engineering-9th-Edition-by-Ian-Sommerville",
         "text": "Agile methods emphasize iterative delivery.", "printed_page": "46"}
qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[
    PointStruct(id=0, vector=[random.random() for _ in range(EMBEDDING_DIM)], payload=chunk)
])

# Monkeypatch the API layer's lazy client getters to return our fakes
clients._openai_client = FakeOpenAIClient()
clients._qdrant_client = qdrant

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password

app = create_app()
test_client = app.test_client()

# Every endpoint exercised below now requires auth -- seed a throwaway
# test user and log in to get a real token, same as the frontend would.
TEST_EMAIL = "test_api_user@example.com"
TEST_PASSWORD = "test-password-123"
with get_session() as session:
    if session.query(User).filter_by(email=TEST_EMAIL).one_or_none() is None:
        session.add(User(email=TEST_EMAIL, password_hash=hash_password(TEST_PASSWORD), is_admin=False))

login_resp = test_client.post("/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
assert login_resp.status_code == 200, login_resp.get_json()
AUTH_HEADERS = {"Authorization": f"Bearer {login_resp.get_json()['access_token']}"}

print("--- POST /api/v1/ask (sync) ---")
r = test_client.post("/api/v1/ask/", json={"question": "What does Sommerville say about agile methods?"}, headers=AUTH_HEADERS)
print(r.status_code)
body = r.get_json()
print(json.dumps(body, indent=2))
assert r.status_code == 200
assert "chat_id" in body and "answer" in body and "citations" in body
chat_id = body["chat_id"]

print("\n--- GET /api/v1/chats/<id> (confirm persistence via the API itself) ---")
r = test_client.get(f"/api/v1/chats/{chat_id}", headers=AUTH_HEADERS)
print(r.status_code)
print(json.dumps(r.get_json(), indent=2)[:600])
assert r.status_code == 200
assert len(r.get_json()["messages"]) == 2

print("\n--- GET /api/v1/chats/<id> WITHOUT auth should be 401 ---")
r = test_client.get(f"/api/v1/chats/{chat_id}")
assert r.status_code == 401

print("\n--- POST /api/v1/ask/stream (SSE) ---")
r = test_client.post("/api/v1/ask/stream", json={"question": "What does Sommerville say about agile methods?"}, headers=AUTH_HEADERS)
print(r.status_code, r.mimetype)
raw = r.get_data(as_text=True)
print(raw[:600])
assert r.status_code == 200
assert r.mimetype == "text/event-stream"
assert "event: chat_id" in raw
assert "event: delta" in raw
assert "event: done" in raw

print("\n--- POST /api/v1/ask with sources scoping to a single book ---")
r = test_client.post("/api/v1/ask/", json={
    "question": "What does Sommerville say about agile methods?",
    "sources": ["Software-Engineering-9th-Edition-by-Ian-Sommerville"],
}, headers=AUTH_HEADERS)
print(r.status_code)
assert r.status_code == 200

print("\nAll API assertions passed.")
