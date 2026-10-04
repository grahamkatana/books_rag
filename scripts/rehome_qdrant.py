"""Re-home existing Qdrant collections from disk-backed storage to RAM.

books_rag's Qdrant was created with `on_disk_payload: true` (global config)
so every cold search reads payload off slow Longhorn disk and blows the 30s
client timeout (measured: cold 38s, warm 3.4s, cached 0.03s).

This script moves the data into RAM by recreating each collection with
`on_disk=False` + `on_disk_payload=False`, re-uploading the *existing*
vectors -- no re-embedding, no OpenAI calls.

Crash-safe: the original collection is only deleted once a complete copy
exists in a temp collection, so the data is always in `name` or `name_ram`
at every step. Idempotent: collections already RAM-resident are skipped, so
re-running after a partial failure just finishes the rest.
"""
import os
import sys
import time

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import Distance, VectorParams, PointStruct

URL = os.environ["QDRANT_URL"]
KEY = os.environ.get("QDRANT_API_KEY")
DIM = int(os.environ.get("EMBEDDING_DIM", "3072"))
COLLECTIONS = [
    os.environ.get("PAPERS_QDRANT_COLLECTION", "paper_library"),
    os.environ.get("QDRANT_COLLECTION", "book_library"),
]
BATCH = 256
RETRIES = 5
TRANSIENT = (httpx.HTTPError, ResponseHandlingException)

client = QdrantClient(url=URL, api_key=KEY, timeout=180)


def count(name: str) -> int:
    return client.get_collection(name).points_count


def already_ram(name: str) -> bool:
    return client.get_collection(name).config.params.on_disk_payload is False


def copy(src: str, dst: str) -> int:
    """Stream every point (id + vector + payload) from src into dst.

    Retries transient connection drops (Qdrant's actix server can drop a
    connection mid-batch). `offset` only advances after a batch is fully
    upserted, so a retry re-reads the same batch rather than skipping it.
    """
    offset = None
    n = 0
    while True:
        for attempt in range(RETRIES):
            try:
                records, new_offset = client.scroll(
                    src, limit=BATCH, offset=offset, with_vectors=True, with_payload=True
                )
                if records:
                    client.upsert(
                        dst,
                        [PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records],
                    )
                    n += len(records)
                offset = new_offset
                break
            except TRANSIENT as e:
                if attempt == RETRIES - 1:
                    raise
                print(f"  retry {attempt + 1} after {type(e).__name__}: {e}", flush=True)
                time.sleep(2 ** attempt)
        if offset is None:
            break
    return n


def wait_count(name: str, expected: int, tries: int = 60) -> int:
    """Poll points_count until it matches expected (Qdrant count can lag)."""
    for _ in range(tries):
        c = count(name)
        if c == expected:
            return c
        time.sleep(2)
    return count(name)


def rehome(name: str) -> None:
    n0 = count(name)
    print(f"=== {name}: {n0} points ===", flush=True)
    if already_ram(name):
        print(f"  already RAM-resident -- skip", flush=True)
        return
    tmp = f"{name}_ram"
    if client.collection_exists(tmp):
        client.delete_collection(tmp)

    # 1. copy original -> temp (RAM), original untouched
    client.create_collection(
        tmp,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE, on_disk=False),
        on_disk_payload=False,
    )
    copied = copy(name, tmp)
    assert copied == n0, f"copy mismatch {name}->{tmp}: {copied} != {n0}"
    print(f"  copied {copied} -> {tmp}", flush=True)

    # 2. swap: delete original, recreate in RAM, copy back from temp
    client.delete_collection(name)
    client.create_collection(
        name,
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE, on_disk=False),
        on_disk_payload=False,
    )
    copied2 = copy(tmp, name)
    assert copied2 == n0, f"recopy mismatch {tmp}->{name}: {copied2} != {n0}"
    print(f"  copied {copied2} -> {name}", flush=True)

    # 3. payload index (idempotent) + verify + cleanup
    client.create_payload_index(name, "source", "keyword")
    final = wait_count(name, n0)
    assert final == n0, f"final count {final} != expected {n0}"
    client.delete_collection(tmp)
    print(f"  DONE {name}: {final} points in RAM", flush=True)


if __name__ == "__main__":
    for name in COLLECTIONS:
        rehome(name)
    print("ALL DONE", flush=True)
