import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION
import app.ingestion.embed_upload as eu


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector

class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]

class FakeOpenAIClient:
    def __init__(self):
        self.call_count = 0
        self.texts_seen = []

    class embeddings:
        pass

    def __post_init__(self):
        pass

# Need call tracking, so build it as an instance with a bound method instead
class TrackedFakeOpenAIClient:
    def __init__(self):
        self.embed_call_count = 0
        self.texts_embedded = []
        outer = self

        class _Embeddings:
            @staticmethod
            def create(model, input):
                outer.embed_call_count += 1
                outer.texts_embedded.extend(input)
                vectors = [[random.random() for _ in range(EMBEDDING_DIM)] for _ in input]
                return FakeEmbeddingResponse(vectors)

        self.embeddings = _Embeddings()


qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

chunks = [
    {"chunk_id": f"book::{i}", "source": "book", "text": f"chunk text number {i}", "printed_page": str(i)}
    for i in range(5)
]

print("=== Run 1: fresh collection, everything should embed ===")
client1 = TrackedFakeOpenAIClient()
result1 = eu.embed_and_upsert(client1, qdrant, chunks, model="text-embedding-3-large")
print(result1)
assert result1["embedded"] == 5
assert result1["skipped"] == 0
assert client1.embed_call_count == 1  # one batch call, 5 texts in it

print("\n=== Run 2: identical rerun, everything should skip ===")
client2 = TrackedFakeOpenAIClient()
result2 = eu.embed_and_upsert(client2, qdrant, chunks, model="text-embedding-3-large")
print(result2)
assert result2["embedded"] == 0
assert result2["skipped"] == 5
assert client2.embed_call_count == 0, "should never call the embeddings API at all when nothing changed"

print("\n=== Run 3: change ONE chunk's text, only that one should re-embed ===")
chunks_modified = [dict(c) for c in chunks]
chunks_modified[2]["text"] = "this text has changed"
client3 = TrackedFakeOpenAIClient()
result3 = eu.embed_and_upsert(client3, qdrant, chunks_modified, model="text-embedding-3-large")
print(result3)
assert result3["embedded"] == 1
assert result3["skipped"] == 4
assert client3.texts_embedded == ["this text has changed"]

print("\n=== Run 4: switch embedding model, EVERYTHING should re-embed despite unchanged text ===")
client4 = TrackedFakeOpenAIClient()
result4 = eu.embed_and_upsert(client4, qdrant, chunks_modified, model="text-embedding-3-small")
print(result4)
assert result4["embedded"] == 5
assert result4["skipped"] == 0

print("\n=== Run 5: force=True bypasses the check even though nothing changed ===")
client5 = TrackedFakeOpenAIClient()
result5 = eu.embed_and_upsert(client5, qdrant, chunks_modified, model="text-embedding-3-small", force=True)
print(result5)
assert result5["embedded"] == 5
assert result5["skipped"] == 0

print("\nAll embed-skip assertions passed.")
