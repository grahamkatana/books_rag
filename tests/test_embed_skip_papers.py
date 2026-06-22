import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION, PAPERS_QDRANT_COLLECTION
import app.ingestion.embed_upload as eu


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector


class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]


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
qdrant.create_collection(PAPERS_QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

paper_chunks = [
    {"chunk_id": f"paper-a::{i}", "source": "paper-a", "text": f"paper chunk text number {i}", "section": "Introduction"}
    for i in range(5)
]

print("=== Run 1: fresh papers collection, everything should embed ===")
client1 = TrackedFakeOpenAIClient()
result1 = eu.embed_and_upsert(client1, qdrant, paper_chunks, model="text-embedding-3-large", collection_name=PAPERS_QDRANT_COLLECTION)
print(result1)
assert result1["embedded"] == 5
assert result1["skipped"] == 0
assert client1.embed_call_count == 1

print("\n=== Run 2: identical rerun against the papers collection, everything should skip ===")
client2 = TrackedFakeOpenAIClient()
result2 = eu.embed_and_upsert(client2, qdrant, paper_chunks, model="text-embedding-3-large", collection_name=PAPERS_QDRANT_COLLECTION)
print(result2)
assert result2["embedded"] == 0
assert result2["skipped"] == 5
assert client2.embed_call_count == 0

print("\n=== The critical check: identical chunk_ids in the BOOKS collection must be treated independently ===")
# Deliberately reuse the exact same chunk_id strings as the paper chunks
# above -- if collection scoping were broken, this would either skip
# (wrongly finding the papers' points) or otherwise interact with them.
# It must behave exactly like a completely fresh, unrelated collection.
book_chunks_with_same_ids = [
    {"chunk_id": f"paper-a::{i}", "source": "some-book", "text": f"a completely different book chunk {i}", "printed_page": str(i)}
    for i in range(5)
]
client3 = TrackedFakeOpenAIClient()
result3 = eu.embed_and_upsert(client3, qdrant, book_chunks_with_same_ids, model="text-embedding-3-large", collection_name=QDRANT_COLLECTION)
print(result3)
assert result3["embedded"] == 5, "identical chunk_ids in a different collection must be treated as entirely new, not skipped"
assert result3["skipped"] == 0

# Confirm the papers collection's actual stored content is untouched --
# still has the ORIGINAL paper text, not overwritten by the books call.
points = qdrant.retrieve(collection_name=PAPERS_QDRANT_COLLECTION, ids=[eu.stable_point_id("paper-a::0")], with_payload=True)
assert points[0].payload["text"] == "paper chunk text number 0", \
    "the papers collection's content must be unaffected by a books upsert using the same chunk_id"
assert points[0].payload["source"] == "paper-a"

# And the books collection has its own distinct content, not the papers'.
points_books = qdrant.retrieve(collection_name=QDRANT_COLLECTION, ids=[eu.stable_point_id("paper-a::0")], with_payload=True)
assert points_books[0].payload["text"] == "a completely different book chunk 0"
assert points_books[0].payload["source"] == "some-book"

print("\nCollection-isolation assertions passed: identical chunk_ids in separate "
      "collections never collide or cross-contaminate.")
print("\nAll embed_upload_papers assertions passed.")