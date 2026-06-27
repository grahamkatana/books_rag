"""
Automatically looks up bibliographic data (title, authors, year,
publisher, edition) for any book in the database that isn't marked
bibliography_verified yet, using web search to find real information
about the book and an LLM to extract structured fields from the
unstructured search results -- writing the result straight into that
book's row.

Brave Search is the primary provider; SerpApi (Google) is an optional
fallback for when Brave fails outright or simply comes back with
nothing usable -- different search backends sometimes have completely
different coverage for the same query, so falling back to a second
one is a real, meaningful improvement, not just redundancy. SerpApi is
genuinely optional throughout: if SERPAPI_API_KEY isn't set, the
fallback is silently skipped and behavior is identical to not having
this at all.

This is the default way a book's bibliography gets improved beyond the
filename guess seed-books gives it on creation. It never touches a row
someone has already verified (whether by hand in /admin or by setting
bibliography_verified=True some other way), and by default won't redo a
row it already auto-looked-up before (pass --force to redo those too).

Costs real money on API keys (Brave Search and/or SerpApi, plus
OpenAI). Results are saved with bibliography_verified still False and
bibliography_source set to "auto_lookup" -- a much better starting
point than a filename guess, but still worth a glance against the real
copyright page (or a quick correction in /admin) before fully trusting
it for citations.

Usage:
    python -m app.cli lookup-bibliography
    python -m app.cli lookup-bibliography --force   # also redo rows already auto-looked-up
"""

import json

from openai import OpenAI
import requests

from app.config import BRAVE_API_KEY, SERPAPI_API_KEY, DEFAULT_CHAT_MODEL
from app.db.session import get_session
from app.models.book import Book
from app.ingestion.bibliography_utils import coerce_bibliography_fields

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPI_API_SEARCH_URL = "https://serpapi.com/search"


def search_brave(query: str, count: int = 5) -> list:
    response = requests.get(
        BRAVE_SEARCH_URL,
        headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
        params={"q": query, "count": count},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("web", {}).get("results", [])


def search_serpapi(query: str, count: int = 5) -> list:
    """Fallback search using SerpApi (Google Search), for when Brave
    fails outright or comes back with nothing usable. Returns results
    normalized to the exact same shape search_brave() already produces
    -- title, url, description -- not SerpApi's own field names (link,
    snippet). extract_bibliography() only ever reads title/url/
    description, so normalizing here means it never needs to know or
    care which provider actually produced a given result.

    Returns an empty list (never raises) if SERPAPI_API_KEY isn't set
    or the request itself fails -- this is always a fallback, never a
    hard dependency, so its own failure should never crash a lookup
    that Brave might still be able to handle."""
    if not SERPAPI_API_KEY:
        return []
    try:
        response = requests.get(
            SERPI_API_SEARCH_URL,
            params={"engine": "google", "q": query, "num": count, "api_key": SERPAPI_API_KEY},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [warning] SerpApi search failed: {e}")
        return []

    organic_results = response.json().get("organic_results", [])
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "description": r.get("snippet", "")}
        for r in organic_results
    ]


def search_with_fallback(query: str, count: int = 5) -> list:
    """Tries Brave first, falls back to SerpApi only if Brave raised or
    came back with nothing -- Brave staying primary (not run in
    parallel with SerpApi) keeps this at one paid search call per book
    in the normal case, with the fallback only spending a second one
    when the first genuinely didn't help."""
    try:
        results = search_brave(query, count=count)
    except requests.RequestException as e:
        print(f"  [warning] Brave search failed: {e} -- trying SerpApi instead")
        results = []

    if results:
        return results
    return search_serpapi(query, count=count)


def extract_bibliography(openai_client, book_hint: str, search_results: list,
                          model: str = DEFAULT_CHAT_MODEL) -> dict:
    """Search results are web page titles/descriptions, not a
    structured bibliography record -- this is the part that actually
    structures it, using the LLM to read the snippets the way a person
    would. Works identically regardless of which provider (Brave or
    SerpApi) produced search_results, since both are normalized to the
    same title/url/description shape before reaching here."""
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
    if not BRAVE_API_KEY and not SERPAPI_API_KEY:
        print("Neither BRAVE_API_KEY nor SERPAPI_API_KEY is set in .env -- skipping "
              "automatic bibliography lookup. Books will keep their filename-guessed "
              "metadata until you set one of these or fix them by hand in /admin.")
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

            results = search_with_fallback(query)

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