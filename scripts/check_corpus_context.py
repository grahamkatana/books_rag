"""
Checks whether the corpus actually "knows" what each book and paper is
about -- the same sense-check an admin already does by hand (start a
chat, ask "what's this about?", judge whether the answer makes sense),
formalized so it can run across the whole library at once instead of
one source at a time.

This exists because ingestion can "succeed" with no error at all and
still produce a source that's effectively useless in the corpus -- a
PDF that failed to chunk meaningfully, a near-empty file, a book that
embedded as mostly garbled OCR text. None of that shows up as a
pipeline failure; retrieval still returns *something*, it's just not
anything coherent. The only way to actually notice is to ask, the same
way a person checking by hand would.

Each book and paper gets its own real chunks retrieved (scoped to just
that one source via source_filter, the same mechanism the chat already
uses to keep one book's answer from blending into another's) and an
LLM judges whether they actually convey a real subject -- not whether
the title sounds plausible, since a bad chunk extraction can still
carry a perfectly reasonable filename.

Results are upserted into corpus_context_checks (one row per book or
paper, re-running this updates the existing row rather than
accumulating duplicates) with marked_for_delete set to match
context_known's negation as a STARTING recommendation -- the actual
decision to delete anything stays a human one. This script only ever
proposes candidates; nothing here deletes anything itself.

Usage:
    uv run python scripts/check_corpus_context.py
    uv run python scripts/check_corpus_context.py --books-only
    uv run python scripts/check_corpus_context.py --papers-only
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEFAULT_CHAT_MODEL
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.corpus_context_check import CorpusContextCheck
from app.api.clients import get_openai_client, get_qdrant_client
from app.retrieval.query_engine import embed_query, search_chunks
from app.logging_config import setup_logging, get_logger

logger = get_logger(__name__)

CONTEXT_CHECK_QUERY = "What is this document about? Summarize its main topic, purpose, and content."

CONTEXT_CHECK_SYSTEM_PROMPT = (
    "You are checking whether retrieved excerpts from a document actually convey what the "
    "document is about. You'll be given the document's title (which may be just a filename "
    "guess, possibly wrong or misleading) and several retrieved chunks of its actual ingested "
    "content. Judge ONLY from the chunks -- a plausible-looking title means nothing if the "
    "actual content is garbled or empty. Respond with ONLY a JSON object: "
    '{"context_known": true/false, "explanation": "..."}. '
    "context_known is true if the chunks clearly convey a real subject, topic, or argument, "
    "even if narrow or technical. context_known is false if the chunks are garbled text, "
    "mostly boilerplate/references/page-numbers/OCR noise, near-empty, or otherwise don't "
    "actually convey what the document is about. explanation is one brief sentence either way."
)


def check_source_context(openai_client, qdrant, source_key: str, corpus: str, title: str, top_k: int = 5) -> tuple[bool, str]:
    """Retrieves this one source's own chunks (and only this source's
    -- source_filter scopes the search exactly the way asking the chat
    "about this specific book" already does) and asks an LLM whether
    they actually convey what it's about. Returns (context_known,
    explanation); never raises -- a failure here is itself meaningful
    information (something's wrong enough that even checking it
    failed), not a reason to crash the whole batch."""
    try:
        query_vector = embed_query(openai_client, CONTEXT_CHECK_QUERY)
        hits = search_chunks(qdrant, query_vector, top_k=top_k, source_filter=source_key, corpus=corpus)
    except Exception as e:
        logger.warning("Retrieval failed for %s: %s", source_key, e)
        return False, f"Retrieval itself failed: {e}"

    if not hits:
        return False, "No chunks at all were retrievable for this source -- it may have failed to embed."

    context = "\n\n".join(h.payload.get("text", "") for h in hits if h.payload.get("text"))
    if not context.strip():
        return False, "Chunks were retrieved but contained no actual text."

    try:
        response = openai_client.chat.completions.create(
            model=DEFAULT_CHAT_MODEL,
            messages=[
                {"role": "system", "content": CONTEXT_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": f"Title (may be imprecise): {title}\n\nRetrieved content:\n\n{context}"},
            ],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        return bool(result.get("context_known", False)), str(result.get("explanation", ""))
    except Exception as e:
        logger.warning("Judgment call failed for %s: %s", source_key, e)
        return False, f"Could not get or parse a judgment: {e}"


def record_check(book_id: int | None, paper_id: int | None, context_known: bool, explanation: str) -> None:
    """Upserts -- updates the existing check for this book/paper if
    one exists, rather than accumulating a new row every time this
    script runs. marked_for_delete is set to context_known's negation
    here as a starting recommendation; an admin reviewing the flagged
    list can still change it independently before this script is ever
    run again."""
    with get_session() as session:
        query = session.query(CorpusContextCheck)
        query = query.filter_by(book_id=book_id) if book_id is not None else query.filter_by(paper_id=paper_id)
        existing = query.one_or_none()
        if existing is not None:
            existing.context_known = context_known
            existing.explanation = explanation
            existing.marked_for_delete = not context_known
            existing.checked_at = datetime.now(timezone.utc)
        else:
            session.add(CorpusContextCheck(
                book_id=book_id, paper_id=paper_id,
                context_known=context_known, explanation=explanation,
                marked_for_delete=not context_known,
            ))


def main(check_books: bool = True, check_papers: bool = True):
    openai_client = get_openai_client()
    qdrant = get_qdrant_client()

    flagged = []

    if check_books:
        with get_session() as session:
            books = [(b.id, b.source_key, b.title) for b in session.query(Book).all()]
        for book_id, source_key, title in books:
            logger.info("Checking book: %s", source_key)
            known, explanation = check_source_context(openai_client, qdrant, source_key, "books", title)
            record_check(book_id=book_id, paper_id=None, context_known=known, explanation=explanation)
            logger.info("  context_known=%s: %s", known, explanation)
            if not known:
                flagged.append(("book", source_key, explanation))

    if check_papers:
        with get_session() as session:
            papers = [(p.id, p.source_key, p.title) for p in session.query(Paper).all()]
        for paper_id, source_key, title in papers:
            logger.info("Checking paper: %s", source_key)
            known, explanation = check_source_context(openai_client, qdrant, source_key, "papers", title)
            record_check(book_id=None, paper_id=paper_id, context_known=known, explanation=explanation)
            logger.info("  context_known=%s: %s", known, explanation)
            if not known:
                flagged.append(("paper", source_key, explanation))

    logger.info("\nDone. %d item(s) flagged (marked_for_delete=True):", len(flagged))
    for item_type, source_key, explanation in flagged:
        logger.info("  [%s] %s -- %s", item_type, source_key, explanation)
    logger.info("\nReview these in /admin before deleting anything -- this script only proposes "
                "candidates, nothing here deletes anything itself.")


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--books-only", action="store_true")
    parser.add_argument("--papers-only", action="store_true")
    args = parser.parse_args()
    main(
        check_books=not args.papers_only,
        check_papers=not args.books_only,
    )