import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION
from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password
import app.api.clients as clients


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector

class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]

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
            return FakeEmbeddingResponse([[random.random() for _ in range(EMBEDDING_DIM)] for _ in input])

    class chat:
        class completions:
            @staticmethod
            def create(model, messages, stream=False):
                if stream:
                    return [FakeStreamChunk(w) for w in ["Hello ", "world."]]

                class _Msg:
                    content = "Hello world."

                class _Choice:
                    message = _Msg()

                class _Response:
                    choices = [_Choice()]

                return _Response()


qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
clients._openai_client = FakeOpenAIClient()
clients._qdrant_client = qdrant

EMAIL_A, PASSWORD_A = "auth_test_user_a@example.com", "password-a-123"
EMAIL_B, PASSWORD_B = "auth_test_user_b@example.com", "password-b-123"

with get_session() as session:
    for email, password in [(EMAIL_A, PASSWORD_A), (EMAIL_B, PASSWORD_B)]:
        if session.query(User).filter_by(email=email).one_or_none() is None:
            session.add(User(email=email, password_hash=hash_password(password), is_admin=False))

app = create_app()
client = app.test_client()


def login(email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["access_token"]


token_a = login(EMAIL_A, PASSWORD_A)
token_b = login(EMAIL_B, PASSWORD_B)
headers_a = {"Authorization": f"Bearer {token_a}"}
headers_b = {"Authorization": f"Bearer {token_b}"}

print("--- user A asks a question, gets a chat ---")
r = client.post("/api/v1/ask/", json={"question": "test?"}, headers=headers_a)
assert r.status_code == 200
chat_id = r.get_json()["chat_id"]

print("--- user A can see their own chat ---")
assert client.get(f"/api/v1/chats/{chat_id}", headers=headers_a).status_code == 200

print("--- user B CANNOT see user A's chat (404, not 403 -- doesn't confirm it exists) ---")
r = client.get(f"/api/v1/chats/{chat_id}", headers=headers_b)
assert r.status_code == 404

print("--- user B trying to continue user A's chat via ask fails cleanly, doesn't crash ---")
r = client.post("/api/v1/ask/", json={"question": "test?", "chat_id": chat_id}, headers=headers_b)
assert r.status_code == 404

print("--- chat lists are isolated per user ---")
assert len(client.get("/api/v1/chats/", headers=headers_a).get_json()) == 1
assert len(client.get("/api/v1/chats/", headers=headers_b).get_json()) == 0

print("--- streaming endpoint requires auth BEFORE any stream starts ---")
r = client.post("/api/v1/ask/stream", json={"question": "test?"})
assert r.status_code == 401

print("--- streaming endpoint works with auth ---")
r = client.post("/api/v1/ask/stream", json={"question": "test?"}, headers=headers_a)
assert r.status_code == 200
raw = r.get_data(as_text=True)
assert "event: chat_id" in raw and "event: delta" in raw and "event: done" in raw

print("\nAll auth/ownership isolation assertions passed.")
