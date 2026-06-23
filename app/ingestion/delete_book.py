"""
Deletes a book completely: its Qdrant vectors, its chunk file, its
manifest entry, and its database row -- the real cleanup operation this
project has never had until now. The REST API and /admin panel both
deliberately never offered book deletion because half of this operation
(just the DB row) would leave the rest permanently orphaned; this is the
other half, finally built.

delete_book() is a plain, non-interactive function on purpose: it never
prompts, never reads stdin, and raises nothing just because something
was already gone. That's specifically so it can be called directly from
anywhere -- this CLI command, a test, or eventually a Celery task
triggered by an admin API endpoint -- without needing a terminal at all.
The interactive confirmation prompt below belongs to the CLI wrapper,
not the function itself.

Order matters: Qdrant vectors and local files are deleted first, each a
safe no-op if already gone, so a failure partway through and a retry of
the whole operation never duplicates work. The database row is deleted
last -- the one truly irreversible step -- so any earlier failure still
leaves a Book row you can see and retry against, rather than a row
silently gone while its orphaned vectors become much harder to find.

Usage:
    python -m app.cli delete-book <source_key>
    python -m app.cli delete-book <source_key> --yes          # skip the interactive confirmation
    python -m app.cli delete-book <source_key> --delete-pdf   # also remove pdfs/books/<source_key>.pdf
"""

from qdrant_client import QdrantClient

from app.config import QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, PDF_DIR, CHUNKS_DIR
from app.db.session import get_session
from app.models.book import Book
from app.ingestion.delete_common import (
    delete_vectors_by_source, delete_chunk_file, remove_manifest_entry, delete_pdf_file,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


def delete_book(source_key: str, delete_pdf: bool = False) -> dict:
    """The actual cleanup operation. Returns a summary dict of what was
    actually found and removed -- every field reflects what genuinely
    happened, not just what was attempted, so a caller (a Celery task,
    eventually) can tell a real deletion apart from a no-op against
    something that was already gone."""
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    vectors_deleted = delete_vectors_by_source(qdrant, source_key, QDRANT_COLLECTION)
    chunk_file_deleted = delete_chunk_file(source_key, CHUNKS_DIR)
    manifest_entry_removed = remove_manifest_entry(source_key, CHUNKS_DIR)
    pdf_deleted = delete_pdf_file(source_key, PDF_DIR) if delete_pdf else False

    db_row_deleted = False
    with get_session() as session:
        book = session.query(Book).filter_by(source_key=source_key).one_or_none()
        if book is not None:
            session.delete(book)
            db_row_deleted = True

    summary = {
        "source_key": source_key,
        "vectors_deleted": vectors_deleted,
        "chunk_file_deleted": chunk_file_deleted,
        "manifest_entry_removed": manifest_entry_removed,
        "pdf_deleted": pdf_deleted,
        "db_row_deleted": db_row_deleted,
    }
    logger.info("Deleted book %s: %s", source_key, summary)
    return summary


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description="Delete a book completely: Qdrant vectors, chunk file, manifest entry, and DB row."
    )
    parser.add_argument("source_key")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
    parser.add_argument("--delete-pdf", action="store_true", help="Also remove the original PDF from pdfs/books/")
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

    summary = delete_book(args.source_key, delete_pdf=args.delete_pdf)
    print(summary)