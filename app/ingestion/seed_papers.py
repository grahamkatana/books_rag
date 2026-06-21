"""
Creates a Paper row for any new PDF in pdfs/papers/ that doesn't have
one yet, using a best-effort title guess from the filename as a
starting point -- the same role seed_books.py plays for books, minus
the page-trust-report step: every paper goes through the same
Docling-based pipeline regardless of its own page-numbering quality, so
there's no trusted/untrusted fork to decide here the way there is for
books.

Never touches an existing row, regardless of where its data came from
(filename guess, DOI lookup, or a manual /admin edit) -- run
lookup-paper-doi next to improve a new row via Crossref, or fix it
directly in /admin.

Usage:
    python -m app.cli seed-papers
"""

import re

from app.config import PAPER_PDF_DIR
from app.db.session import get_session
from app.models.paper import Paper
from app.logging_config import get_logger

logger = get_logger(__name__)


def guess_title_from_filename(stem: str) -> str:
    """Best-effort and deliberately conservative -- this exists only so
    a brand-new row has something before lookup-paper-doi (or a manual
    edit) improves it. Papers' filenames are often already close to the
    real title (unlike books', which are full of edition/publisher
    noise), so this is intentionally simpler than seed_books.py's
    filename-guessing heuristic."""
    cleaned = re.sub(r"[_\-]+", " ", stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or stem


def main():
    if not PAPER_PDF_DIR.exists():
        logger.warning("%s does not exist -- nothing to seed", PAPER_PDF_DIR)
        return

    pdf_files = sorted(PAPER_PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", PAPER_PDF_DIR)
        return

    created = 0
    with get_session() as session:
        for pdf_path in pdf_files:
            source_key = pdf_path.stem
            existing = session.query(Paper).filter_by(source_key=source_key).one_or_none()
            if existing is not None:
                logger.info("[unchanged] %s: already in the database, leaving it alone", source_key)
                continue

            title = guess_title_from_filename(source_key)
            paper = Paper(
                source_key=source_key,
                title=title,
                bibliography_verified=False,
                bibliography_source="filename_guess",
            )
            session.add(paper)
            created += 1
            logger.info("[new] %s -> title=%r", source_key, title)

    logger.info("Done. %d new paper(s) added.", created)


if __name__ == "__main__":
    main()