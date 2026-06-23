"""
Embeds chunked paper text (data/papers/chunks/*.jsonl) with OpenAI and
upserts into PAPERS_QDRANT_COLLECTION -- a separate collection from
books, on purpose, so a book question's retrieval can never surface
paper noise or vice versa.

A thin wrapper around embed_upload.py's own functions rather than a
parallel reimplementation: the actual embedding/skip-cache/upsert logic
is identical to the books pipeline, just pointed at a different chunks
directory and a different collection name.

Usage:
    python -m app.cli embed-papers
    python -m app.cli embed-papers --force
"""

from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import PAPERS_CHUNKS_DIR, PAPERS_QDRANT_COLLECTION, QDRANT_URL, QDRANT_API_KEY, QDRANT_TIMEOUT
from app.ingestion.embed_upload import ensure_collection, load_all_chunks, embed_and_upsert
from app.logging_config import get_logger

logger = get_logger(__name__)


def main(force: bool = False):
    openai_client = OpenAI()
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=QDRANT_TIMEOUT)

    ensure_collection(qdrant, collection_name=PAPERS_QDRANT_COLLECTION)
    chunks = load_all_chunks(chunks_dir=PAPERS_CHUNKS_DIR)
    if not chunks:
        logger.warning("No chunk files found in %s. Run chunk-papers first.", PAPERS_CHUNKS_DIR)
        return

    logger.info("Loaded %d paper chunk(s). Checking against what's already in Qdrant...", len(chunks))
    result = embed_and_upsert(openai_client, qdrant, chunks, force=force, collection_name=PAPERS_QDRANT_COLLECTION)
    logger.info("Done. %d chunk(s) embedded/updated, %d unchanged and skipped, in collection '%s'.",
                result["embedded"], result["skipped"], PAPERS_QDRANT_COLLECTION)


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)