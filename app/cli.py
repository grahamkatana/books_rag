"""
Unified CLI for the book RAG pipeline.

Usage:
    python -m app.cli report
    python -m app.cli seed-books
    python -m app.cli lookup-bibliography
    python -m app.cli chunk
    python -m app.cli embed
    python -m app.cli ask "question" [--chat-id N] [--source NAME ...] [--top-k N] [--model NAME]

Database tables are managed via Alembic directly, not through this CLI:
    alembic upgrade head
"""

import argparse

from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import QDRANT_URL, QDRANT_API_KEY, DEFAULT_CHAT_MODEL, DEFAULT_TOP_K
from app.db.session import get_session
from app.retrieval.query_engine import answer_question
from app.logging_config import setup_logging


def cmd_report(args):
    from app.ingestion.build_trust_report import main as run
    run()


def cmd_chunk(args):
    from app.ingestion.chunk_trusted_books import main as run_trusted
    from app.ingestion.chunk_untrusted_books import main as run_untrusted
    force = getattr(args, "force", False)
    run_trusted(force=force)
    run_untrusted(force=force)


def cmd_seed_books(args):
    from app.ingestion.seed_books import main as run
    run()


def cmd_lookup_bibliography(args):
    from app.ingestion.lookup_bibliography import main as run
    run(force=getattr(args, "force", False))


def cmd_seed_papers(args):
    from app.ingestion.seed_papers import main as run
    run()


def cmd_lookup_paper_doi(args):
    from app.ingestion.lookup_paper_doi import main as run
    run(force=getattr(args, "force", False))


def cmd_chunk_papers(args):
    from app.ingestion.chunk_papers import main as run
    run(force=getattr(args, "force", False))


def cmd_embed_papers(args):
    from app.ingestion.embed_upload_papers import main as run
    run(force=getattr(args, "force", False))


def cmd_embed(args):
    from app.ingestion.embed_upload import main as run
    run(force=getattr(args, "force", False))


def cmd_delete_book(args):
    from app.ingestion.delete_book import delete_book
    if not args.yes:
        confirm = input(
            f"This will permanently delete '{args.source_key}': its Qdrant vectors, chunk file, "
            f"and database row{' and its source PDF' if args.delete_pdf else ''}. "
            f"This cannot be undone. Type 'yes' to confirm: "
        )
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            return
    summary = delete_book(args.source_key, delete_pdf=args.delete_pdf)
    print(summary)


def cmd_delete_paper(args):
    from app.ingestion.delete_paper import delete_paper
    if not args.yes:
        confirm = input(
            f"This will permanently delete '{args.source_key}': its Qdrant vectors, chunk file, "
            f"and database row{' and its source PDF' if args.delete_pdf else ''}. "
            f"This cannot be undone. Type 'yes' to confirm: "
        )
        if confirm.strip().lower() != "yes":
            print("Cancelled.")
            return
    summary = delete_paper(args.source_key, delete_pdf=args.delete_pdf)
    print(summary)


def cmd_pipeline(args):
    # seed-books only needs to run once now: it creates a Book row for
    # any new file (filename-guessed, unverified) and never touches an
    # existing one. lookup-bibliography then improves those rows
    # directly in the database -- there's no JSON file in between
    # anymore, so there's nothing to bootstrap-then-reapply.
    steps = [
        ("report", cmd_report),
        ("seed-books", cmd_seed_books),
        ("lookup-bibliography", cmd_lookup_bibliography),
        ("chunk", cmd_chunk),
        ("embed", cmd_embed),
    ]
    for i, (name, fn) in enumerate(steps, start=1):
        print(f"\n=== Step {i}/{len(steps)}: {name} ===")
        try:
            fn(args)
        except SystemExit as e:
            print(f"\nPipeline stopped at step {i} ({name}): {e}")
            raise
        except Exception as e:
            print(f"\nPipeline stopped at step {i} ({name}) due to an unexpected error: {e}")
            raise
    print("\nPipeline complete -- the library is ready to query.")


def cmd_pipeline_papers(args):
    # No report step here, unlike the books pipeline -- papers don't
    # have a trusted/untrusted chunking fork to decide between, so
    # there's nothing for a report to determine in advance. seed-papers
    # only needs to run once per new file too, same reasoning as
    # seed-books: it never touches a row that already exists.
    steps = [
        ("seed-papers", cmd_seed_papers),
        ("lookup-paper-doi", cmd_lookup_paper_doi),
        ("chunk-papers", cmd_chunk_papers),
        ("embed-papers", cmd_embed_papers),
    ]
    for i, (name, fn) in enumerate(steps, start=1):
        print(f"\n=== Step {i}/{len(steps)}: {name} ===")
        try:
            fn(args)
        except SystemExit as e:
            print(f"\nPipeline stopped at step {i} ({name}): {e}")
            raise
        except Exception as e:
            print(f"\nPipeline stopped at step {i} ({name}) due to an unexpected error: {e}")
            raise
    print("\nPapers pipeline complete -- the papers library is ready to query (pass corpus='papers' or 'both' when asking).")


def cmd_ask(args):
    openai_client = OpenAI()
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    with get_session() as session:
        result = answer_question(
            session, openai_client, qdrant,
            question=args.question,
            chat_id=args.chat_id,
            source_filter=args.source,
            top_k=args.top_k,
            model=args.model,
            all_editions=args.all_editions,
            corpus=args.corpus,
        )

    print(f"\nChat ID: {result['chat_id']} (pass --chat-id {result['chat_id']} to continue this conversation)\n")
    print(result["answer"])
    print("\n--- Citations ---")
    for c in result["citations"]:
        print(f"  {c['apa_text']}")


def main():
    setup_logging()

    parser = argparse.ArgumentParser(description="Book RAG CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Build data/report.csv (which books have trustworthy page numbers)").set_defaults(func=cmd_report)

    chunk_parser = sub.add_parser("chunk", help="Chunk trusted books into data/chunks/*.jsonl")
    chunk_parser.add_argument("--force", action="store_true", help="Re-chunk every book, even unchanged ones")
    chunk_parser.set_defaults(func=cmd_chunk)

    sub.add_parser("seed-books", help="Create a Book row (filename-guessed, unverified) for any new file in the report").set_defaults(func=cmd_seed_books)

    lookup_parser = sub.add_parser("lookup-bibliography",
                                    help="Improve any unverified book's bibliography via Brave Search + LLM extraction (needs BRAVE_API_KEY)")
    lookup_parser.add_argument("--force", action="store_true", help="Redo entries already auto-looked-up, not just missing ones")
    lookup_parser.set_defaults(func=cmd_lookup_bibliography)

    # Papers pipeline -- standalone for now, deliberately not part of
    # `pipeline` yet, since paper chunking/embedding don't exist as
    # steps to run after this. Will join `pipeline` once that's built.
    sub.add_parser("seed-papers", help="Create a Paper row (filename-guessed, unverified) for any new file in pdfs/papers/").set_defaults(func=cmd_seed_papers)

    paper_doi_parser = sub.add_parser("lookup-paper-doi",
                                       help="Resolve any unverified paper's real bibliography via its DOI (Crossref) -- no API key needed")
    paper_doi_parser.add_argument("--force", action="store_true", help="Redo entries already DOI-looked-up, not just missing ones")
    paper_doi_parser.set_defaults(func=cmd_lookup_paper_doi)

    chunk_papers_parser = sub.add_parser("chunk-papers", help="Chunk papers in pdfs/papers/ via Docling into data/papers/chunks/*.jsonl")
    chunk_papers_parser.add_argument("--force", action="store_true", help="Re-chunk every paper, even unchanged ones")
    chunk_papers_parser.set_defaults(func=cmd_chunk_papers)

    embed_papers_parser = sub.add_parser("embed-papers", help="Embed paper chunks and upsert into the separate papers Qdrant collection")
    embed_papers_parser.add_argument("--force", action="store_true", help="Re-embed every paper chunk, even unchanged ones")
    embed_papers_parser.set_defaults(func=cmd_embed_papers)

    embed_parser = sub.add_parser("embed", help="Embed chunks and upsert into Qdrant")
    embed_parser.add_argument("--force", action="store_true", help="Re-embed every chunk, even unchanged ones")
    embed_parser.set_defaults(func=cmd_embed)

    delete_book_parser = sub.add_parser("delete-book", help="Permanently delete a book: vectors, chunk file, manifest entry, and DB row")
    delete_book_parser.add_argument("source_key")
    delete_book_parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
    delete_book_parser.add_argument("--delete-pdf", action="store_true", help="Also remove the original PDF from pdfs/books/")
    delete_book_parser.set_defaults(func=cmd_delete_book)

    delete_paper_parser = sub.add_parser("delete-paper", help="Permanently delete a paper: vectors, chunk file, manifest entry, and DB row")
    delete_paper_parser.add_argument("source_key")
    delete_paper_parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
    delete_paper_parser.add_argument("--delete-pdf", action="store_true", help="Also remove the original PDF from pdfs/papers/")
    delete_paper_parser.set_defaults(func=cmd_delete_paper)

    pipeline_parser = sub.add_parser("pipeline", help="Run report, seed-books, lookup-bibliography, chunk, and embed in sequence")
    pipeline_parser.add_argument("--force", action="store_true", help="Force the chunk and embed steps to reprocess everything")
    pipeline_parser.set_defaults(func=cmd_pipeline)

    pipeline_papers_parser = sub.add_parser("pipeline-papers", help="Run seed-papers, lookup-paper-doi, chunk-papers, and embed-papers in sequence")
    pipeline_papers_parser.add_argument("--force", action="store_true", help="Force every step to reprocess everything, not just unverified/unchanged items")
    pipeline_papers_parser.set_defaults(func=cmd_pipeline_papers)

    ask_parser = sub.add_parser("ask", help="Ask a question against the library")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--chat-id", type=int, default=None, help="Continue an existing chat instead of starting a new one")
    ask_parser.add_argument("--source", action="append", default=None,
                             help="Restrict search to a book's source_key. Repeat for multiple books, e.g. --source bookA --source bookB")
    ask_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ask_parser.add_argument("--model", default=DEFAULT_CHAT_MODEL)
    ask_parser.add_argument("--all-editions", action="store_true",
                             help="Search every edition of a book instead of just the preferred one")
    ask_parser.add_argument("--corpus", choices=["books", "papers", "both"], default="books",
                             help="Which library to search: books (default), papers, or both")
    ask_parser.set_defaults(func=cmd_ask)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()