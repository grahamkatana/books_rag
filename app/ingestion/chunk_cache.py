"""
Shared skip-cache logic for chunking scripts. chunk_trusted_books.py and
chunk_untrusted_books.py share one manifest (the default, CHUNKS_DIR);
chunk_papers.py uses the same logic against PAPERS_CHUNKS_DIR instead, by
passing chunks_dir explicitly -- so a book added by one pipeline doesn't
get silently reprocessed by logic duplicated elsewhere, and papers never
share a manifest with books at all.
"""

import json
import hashlib

from app.config import CHUNKS_DIR


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(chunks_dir=CHUNKS_DIR) -> dict:
    manifest_path = chunks_dir / ".manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    return {}


def save_manifest(manifest: dict, chunks_dir=CHUNKS_DIR) -> None:
    (chunks_dir / ".manifest.json").write_text(json.dumps(manifest, indent=2))


def is_unchanged(manifest: dict, book_title: str, current_hash: str,
                  settings: dict, out_path) -> bool:
    """settings is whatever chunking-relevant config this pipeline used
    (chunk size/overlap, heading thresholds, etc.) -- compared as-is, so
    any change to it invalidates the cache for that book."""
    cached = manifest.get(book_title)
    return (
        cached is not None
        and cached.get("pdf_sha256") == current_hash
        and cached.get("settings") == settings
        and out_path.exists()
    )


def update_manifest(manifest: dict, book_title: str, current_hash: str, settings: dict) -> None:
    manifest[book_title] = {"pdf_sha256": current_hash, "settings": settings}