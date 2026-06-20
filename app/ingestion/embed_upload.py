"""
Embeds chunked book text (data/chunks/*.jsonl) with OpenAI and upserts
into Qdrant. Re-running is safe: point IDs are derived deterministically
from chunk_id, so existing chunks are overwritten rather than duplicated.

Skips re-embedding a chunk if it already exists in Qdrant with identical
text, embedded with the same model -- otherwise every run would re-embed
your whole library (real OpenAI cost) just because one new book got
added. Switching EMBEDDING_MODEL invalidates everything automatically,
since the stored model is checked too. Pass force=True (or --force on
the CLI) to re-embed everything regardless.

Usage:
    python -m app.ingestion.embed_upload
    python -m app.ingestion.embed_upload --force
"""

import json
import glob
import hashlib

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import (
    CHUNKS_DIR, QDRANT_COLLECTION, QDRANT_URL, QDRANT_API_KEY,
    EMBEDDING_MODEL, EMBEDDING_DIM,
)

BATCH_SIZE = 100


def ensure_collection(qdrant: QdrantClient):
    if not qdrant.collection_exists(QDRANT_COLLECTION):
        qdrant.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection '{QDRANT_COLLECTION}' ({EMBEDDING_DIM}-dim, cosine).")


def load_all_chunks(chunks_dir=CHUNKS_DIR) -> list:
    chunks = []
    for path in sorted(glob.glob(str(chunks_dir / "*.jsonl"))):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
    return chunks


def embed_batch(openai_client, texts: list, model: str = EMBEDDING_MODEL) -> list:
    response = openai_client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def stable_point_id(chunk_id: str) -> int:
    return int(hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:16], 16)


def get_existing_payloads(qdrant: QdrantClient, point_ids: list) -> dict:
    """Batch-retrieves whichever of these point ids already exist, keyed
    by id. IDs that don't exist yet are simply absent from the result."""
    if not point_ids:
        return {}
    records = qdrant.retrieve(
        collection_name=QDRANT_COLLECTION, ids=point_ids, with_payload=True, with_vectors=False
    )
    return {r.id: r.payload for r in records}


def embed_and_upsert(openai_client, qdrant: QdrantClient, chunks: list,
                      model: str = EMBEDDING_MODEL, batch_size: int = BATCH_SIZE,
                      force: bool = False) -> dict:
    embedded = 0
    skipped = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        ids = [stable_point_id(c["chunk_id"]) for c in batch]
        existing = {} if force else get_existing_payloads(qdrant, ids)

        to_embed, to_embed_ids = [], []
        for c, pid in zip(batch, ids):
            prior = existing.get(pid)
            unchanged = (
                prior is not None
                and prior.get("text") == c["text"]
                and prior.get("_embedding_model") == model
            )
            if unchanged:
                skipped += 1
            else:
                to_embed.append(c)
                to_embed_ids.append(pid)

        if not to_embed:
            continue

        texts = [c["text"] for c in to_embed]
        embeddings = embed_batch(openai_client, texts, model=model)

        points = [
            PointStruct(id=pid, vector=v, payload={**c, "_embedding_model": model})
            for c, v, pid in zip(to_embed, embeddings, to_embed_ids)
        ]
        qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
        embedded += len(points)
        print(f"  embedded {embedded} new/changed, skipped {skipped} unchanged "
              f"({min(i + batch_size, len(chunks))}/{len(chunks)} checked)")

    return {"embedded": embedded, "skipped": skipped}


def main(force: bool = False):
    openai_client = OpenAI()
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    ensure_collection(qdrant)
    chunks = load_all_chunks()
    if not chunks:
        print(f"No chunk files found in {CHUNKS_DIR}. Run chunk_trusted_books first.")
        return

    print(f"Loaded {len(chunks)} chunks. Checking against what's already in Qdrant...")
    result = embed_and_upsert(openai_client, qdrant, chunks, force=force)
    print(f"\nDone. {result['embedded']} chunk(s) embedded/updated, "
          f"{result['skipped']} unchanged and skipped, "
          f"in collection '{QDRANT_COLLECTION}'.")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
