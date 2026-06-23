"""
Generic delete helpers shared by delete_book.py and delete_paper.py --
the same DRY pattern embed_upload.py/embed_upload_papers.py already
follows: one real implementation, parameterized by which collection/
directory to act on, rather than two copies that can drift apart.

Every function here is deliberately idempotent: deleting something
that's already gone is a safe no-op, not an error. That matters because
the whole delete operation built on top of these (see delete_book.py)
is designed to be safely re-run from the top if it fails partway
through -- a background worker retrying a failed job should never
error out or duplicate work just because some of it already happened.
"""

from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, FilterSelector

from app.ingestion.chunk_cache import load_manifest, save_manifest


def delete_vectors_by_source(qdrant: QdrantClient, source_key: str, collection_name: str) -> int:
    """Deletes every point in the collection whose payload "source"
    matches this source_key, by filter rather than needing to know
    point IDs ahead of time. Returns how many points were actually
    deleted (counted first, since Qdrant's delete-by-filter doesn't
    report this on its own)."""
    if not qdrant.collection_exists(collection_name):
        return 0
    source_filter = Filter(must=[FieldCondition(key="source", match=MatchValue(value=source_key))])
    count_before = qdrant.count(collection_name=collection_name, count_filter=source_filter).count
    if count_before == 0:
        return 0
    qdrant.delete(collection_name=collection_name, points_selector=FilterSelector(filter=source_filter))
    return count_before


def delete_chunk_file(source_key: str, chunks_dir: Path) -> bool:
    chunk_path = chunks_dir / f"{source_key}.jsonl"
    if chunk_path.exists():
        chunk_path.unlink()
        return True
    return False


def remove_manifest_entry(source_key: str, chunks_dir: Path) -> bool:
    manifest = load_manifest(chunks_dir=chunks_dir)
    if source_key in manifest:
        del manifest[source_key]
        save_manifest(manifest, chunks_dir=chunks_dir)
        return True
    return False


def delete_pdf_file(source_key: str, pdf_dir: Path) -> bool:
    pdf_path = pdf_dir / f"{source_key}.pdf"
    if pdf_path.exists():
        pdf_path.unlink()
        return True
    return False