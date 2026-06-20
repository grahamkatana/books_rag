"""
Automatically looks up bibliographic data (title, authors, year,
publisher, edition) for any book in the database that isn't marked
bibliography_verified yet, using Brave Search to find real information
about the book and an LLM to extract structured fields from the
unstructured search results -- writing the result straight into that
book's row.

This is the default way a book's bibliography gets improved beyond the
filename guess seed-books gives it on creation. It never touches a row
someone has already verified (whether by hand in /admin or by setting
bibliography_verified=True some other way), and by default won't redo a
row it already auto-looked-up before (pass --force to redo those too).

Costs real money on two API keys (Brave Search + OpenAI). Results are
saved with bibliography_verified still False and bibliography_source
set to "auto_lookup" -- a much better starting point than a filename
guess, but still worth a glance against the real copyright page (or a
quick correction in /admin) before fully trusting it for citations.

Usage:
    python -m app.cli lookup-bibliography
    python -m app.cli lookup-bibliography --force   # also redo rows already auto-looked-up
"""

import json

from openai import OpenAI
import requests

from app.config import BRAVE_API_KEY, DEFAULT_CHAT_MODEL
from app.db.session import get_session
from app.models.book import Book
from app.ingestion.bibliography_utils import coerce_bibliography_fields

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def search_brave(query: str, count: int = 5) -> list:
    response = requests.get(
        BRAVE_SEARCH_URL,
        headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
        params={"q": query, "count": count},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("web", {}).get("results", [])


def extract_bibliography(openai_client, book_hint: str, search_results: list,
                          model: str = DEFAULT_CHAT_MODEL) -> dict:
    """Brave returns web page titles/descriptions, not a structured
    bibliography record -- this is the part that actually structures it,
    using the LLM to read the snippets the way a person would."""
    if not search_results:
        return {}

    context = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('description', '')}"
        for r in search_results
    )

    system_prompt = (
        "You extract bibliographic data about a specific book from web "
        "search results. Respond with ONLY a JSON object with these exact "
        "keys: title, authors, year, publisher, edition, is_editor, "
        "confidence. authors should be in 'Surname, F.' format (e.g. "
        "'Sommerville, I.'), or the editor's surname if is_editor is true. "
        "year is an integer or null. edition is a short string like '3rd "
        "ed.' or null. confidence is \"high\", \"medium\", or \"low\" based "
        "on how consistent the search results are with each other -- if "
        "results disagree, seem thin, or seem to be about a different book "
        "entirely, say low rather than guessing. Use null for any field you "
        "can't determine confidently."
    )
    user_prompt = f"Book (from filename, may be imprecise): {book_hint}\n\nSearch results:\n\n{context}"

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return coerce_bibliography_fields(json.loads(response.choices[0].message.content))
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}


def main(force: bool = False):
    if not BRAVE_API_KEY:
        print("BRAVE_API_KEY not set in .env -- skipping automatic bibliography "
              "lookup. Books will keep their filename-guessed metadata until "
              "you set this or fix them by hand in /admin.")
        return

    openai_client = OpenAI()

    with get_session() as session:
        query_filter = Book.bibliography_verified.is_(False)
        if not force:
            query_filter = query_filter & (Book.bibliography_source != "auto_lookup")
        books = session.query(Book).filter(query_filter).all()

        if not books:
            print("Nothing to look up -- every book is either verified or "
                  "already auto-looked-up (pass --force to redo those too).")
            return

        for book in books:
            query = f"{book.title} book"
            print(f"Looking up: {query!r}")

            try:
                results = search_brave(query)
            except requests.RequestException as e:
                print(f"  [error] Brave search failed for {book.source_key}: {e}")
                continue

            found = extract_bibliography(openai_client, book.source_key, results)
            if not found or not found.get("title"):
                print(f"  [no result] couldn't extract a bibliography for {book.source_key}")
                continue

            confidence = found.pop("confidence", "low")
            book.title = found.get("title") or book.title
            book.authors = found.get("authors")
            book.is_editor = bool(found.get("is_editor", False))
            book.year = found.get("year")
            book.publisher = found.get("publisher")
            book.edition = found.get("edition")
            book.bibliography_source = "auto_lookup"
            book.lookup_confidence = confidence
            session.add(book)

            print(f"  [{confidence} confidence] {book.source_key} -> "
                  f"title={book.title!r} authors={book.authors!r} year={book.year}")

    print("\nDone. Review books with bibliography_source='auto_lookup' in "
          "/admin -- set them verified once you've checked one against the "
          "real copyright page.")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)
