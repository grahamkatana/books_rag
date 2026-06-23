"""
One-off backfill for libraries that already existed before this fix:
creates the payload index on "source" for both book_library and
paper_library directly, without needing to re-run the full embed
pipeline. Safe to run regardless of whether the index already exists
(create_payload_index is idempotent) or whether a collection doesn't
exist yet (skipped with a clear message, not an error).

Why this exists as a separate script rather than just relying on the
fix in embed_upload.py's ensure_collection(): that fix only takes effect
the next time you run `embed`/`embed-papers`. If your library already
has many chunks in it, every filtered Qdrant operation until then --
including delete-book/delete-paper -- keeps paying the same unindexed
full-payload-scan cost this fix exists to remove. Run this once, now,
to apply it immediately to what's already there.

Usage:
    uv run python scripts/create_payload_indexes.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.http.models import PayloadSchemaType

from app.config import QDRANT_URL, QDRANT_API_KEY, QDRANT_TIMEOUT, QDRANT_COLLECTION, PAPERS_QDRANT_COLLECTION


def ensure_source_index(qdrant: QdrantClient, collection_name: str) -> None:
    if not qdrant.collection_exists(collection_name):
        print(f"[skip] {collection_name}: collection doesn't exist yet -- nothing to index.")
        return
    qdrant.create_payload_index(
        collection_name=collection_name,
        field_name="source",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    print(f"[done] {collection_name}: payload index on 'source' created (or already existed).")


def main():
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=QDRANT_TIMEOUT)
    ensure_source_index(qdrant, QDRANT_COLLECTION)
    ensure_source_index(qdrant, PAPERS_QDRANT_COLLECTION)
    print("\nDone. Filtered operations (search scoping, edition exclusion, "
          "delete-by-source) against these collections should no longer "
          "need a full unindexed payload scan.")


if __name__ == "__main__":
    main()