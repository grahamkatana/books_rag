"""
Deletes a paper completely: its Qdrant vectors, its chunk file, its
manifest entry, and its database row -- mirrors delete_book.py exactly,
same reasoning throughout, just pointed at Paper / PAPERS_QDRANT_COLLECTION
/ PAPERS_CHUNKS_DIR / PAPER_PDF_DIR instead.

delete_paper() is a plain, non-interactive function on purpose: it never
prompts, never reads stdin, and raises nothing just because something
was already gone -- so it can be called directly from anywhere (this
CLI command, a test, or eventually a Celery task) without needing a
terminal at all. The interactive confirmation prompt belongs to the CLI
wrapper, not the function itself.

Order matters: Qdrant vectors and local files are deleted first, each a
safe no-op if already gone, so a failure partway through and a retry of
the whole operation never duplicates work. The database row is deleted
last -- the one truly irreversible step.

Usage:
    python -m app.cli delete-paper <source_key>
    python -m app.cli delete-paper <source_key> --yes          # skip the interactive confirmation
    python -m app.cli delete-paper <source_key> --delete-pdf   # also remove pdfs/papers/<source_key>.pdf
"""

from qdrant_client import QdrantClient

from app.config import QDRANT_URL, QDRANT_API_KEY, PAPERS_QDRANT_COLLECTION, PAPER_PDF_DIR, PAPERS_CHUNKS_DIR
from app.db.session import get_session
from app.models.paper import Paper
from app.ingestion.delete_common import (
    delete_vectors_by_source, delete_chunk_file, remove_manifest_entry, delete_pdf_file,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


def delete_paper(source_key: str, delete_pdf: bool = False) -> dict:
    """The actual cleanup operation. Returns a summary dict of what was
    actually found and removed -- every field reflects what genuinely
    happened, not just what was attempted."""
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    vectors_deleted = delete_vectors_by_source(qdrant, source_key, PAPERS_QDRANT_COLLECTION)
    chunk_file_deleted = delete_chunk_file(source_key, PAPERS_CHUNKS_DIR)
    manifest_entry_removed = remove_manifest_entry(source_key, PAPERS_CHUNKS_DIR)
    pdf_deleted = delete_pdf_file(source_key, PAPER_PDF_DIR) if delete_pdf else False

    db_row_deleted = False
    with get_session() as session:
        paper = session.query(Paper).filter_by(source_key=source_key).one_or_none()
        if paper is not None:
            session.delete(paper)
            db_row_deleted = True

    summary = {
        "source_key": source_key,
        "vectors_deleted": vectors_deleted,
        "chunk_file_deleted": chunk_file_deleted,
        "manifest_entry_removed": manifest_entry_removed,
        "pdf_deleted": pdf_deleted,
        "db_row_deleted": db_row_deleted,
    }
    logger.info("Deleted paper %s: %s", source_key, summary)
    return summary


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Delete a paper completely: Qdrant vectors, chunk file, manifest entry, and DB row."
    )
    parser.add_argument("source_key")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
    parser.add_argument("--delete-pdf", action="store_true", help="Also remove the original PDF from pdfs/papers/")
    args = parser.parse_args()

    if not args.yes:
        confirm = input(
            f"This will permanently delete '{args.source_key}': its Qdrant vectors, chunk file, "
            f"and database row{' and its source PDF' if args.delete_pdf else ''}. "
            f"This cannot be undone. Type 'yes' to confirm: "
        )
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            sys.exit(0)

    summary = delete_paper(args.source_key, delete_pdf=args.delete_pdf)
    print(summary)