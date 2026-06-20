import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION
from app.retrieval.query_engine import search_chunks

qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

chunks = [
    {"chunk_id": "ninth::1", "source": "Software-Engineering-9th-Edition-by-Ian-Sommerville",
     "text": "9th edition content", "printed_page": "6"},
    {"chunk_id": "eighth::1", "source": "Software-Engineering-8th-Edition-by-Ian-Sommerville",
     "text": "8th edition content", "printed_page": "6"},
    {"chunk_id": "clrs::1", "source": "Introduction-to-Algorithms-4th",
     "text": "CLRS content", "printed_page": "2"},
]
points = [PointStruct(id=i, vector=[random.random() for _ in range(EMBEDDING_DIM)], payload=c)
          for i, c in enumerate(chunks)]
qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)

query_vector = [random.random() for _ in range(EMBEDDING_DIM)]

print("--- default: exclude the 8th edition ---")
hits = search_chunks(qdrant, query_vector, top_k=10, exclude_source_keys=["Software-Engineering-8th-Edition-by-Ian-Sommerville"])
sources = [h.payload["source"] for h in hits]
print(sources)
assert "Software-Engineering-8th-Edition-by-Ian-Sommerville" not in sources
assert "Software-Engineering-9th-Edition-by-Ian-Sommerville" in sources

print("\n--- --all-editions: no exclusion, both should be findable ---")
hits = search_chunks(qdrant, query_vector, top_k=10, exclude_source_keys=[])
sources = [h.payload["source"] for h in hits]
print(sources)
assert "Software-Engineering-8th-Edition-by-Ian-Sommerville" in sources

print("\n--- explicit --source targeting the OLD edition: should win over exclusion ---")
hits = search_chunks(qdrant, query_vector, top_k=10,
                      source_filter="Software-Engineering-8th-Edition-by-Ian-Sommerville",
                      exclude_source_keys=["Software-Engineering-8th-Edition-by-Ian-Sommerville"])
sources = [h.payload["source"] for h in hits]
print(sources)
assert sources == ["Software-Engineering-8th-Edition-by-Ian-Sommerville"]

print("\n--- multi-source: a LIST of two books should return chunks from exactly those two ---")
hits = search_chunks(qdrant, query_vector, top_k=10,
                      source_filter=["Software-Engineering-9th-Edition-by-Ian-Sommerville", "Introduction-to-Algorithms-4th"])
sources = sorted(h.payload["source"] for h in hits)
print(sources)
assert sources == ["Introduction-to-Algorithms-4th", "Software-Engineering-9th-Edition-by-Ian-Sommerville"]
assert "Software-Engineering-8th-Edition-by-Ian-Sommerville" not in sources

print("\n--- multi-source list explicitly including a non-preferred edition: should still win over exclusion ---")
hits = search_chunks(qdrant, query_vector, top_k=10,
                      source_filter=["Software-Engineering-8th-Edition-by-Ian-Sommerville", "Introduction-to-Algorithms-4th"],
                      exclude_source_keys=["Software-Engineering-8th-Edition-by-Ian-Sommerville"])
sources = sorted(h.payload["source"] for h in hits)
print(sources)
assert sources == ["Introduction-to-Algorithms-4th", "Software-Engineering-8th-Edition-by-Ian-Sommerville"]

print("\nAll filter assertions passed.")
