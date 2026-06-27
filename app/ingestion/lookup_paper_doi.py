"""
Finds and resolves each unverified paper's real DOI, then writes
structured bibliographic data (title, authors, year, venue, abstract)
straight into its Paper row -- the papers' equivalent of
lookup_bibliography.py, but using Crossref's actual structured metadata
API instead of web-search-and-LLM-extraction, since a DOI resolves to
one specific, verifiable record rather than a pile of search snippets
to interpret.

Two-step resolution per paper:
  1. Try to find the paper's own DOI printed on its first couple of
     pages (a "doi:" / "doi.org/"-labeled match is tried before a bare
     DOI-shaped string, since a bare match that early in a paper could
     just as easily belong to something it cites rather than the paper
     itself -- reference lists don't start that early, but a labeled
     self-citation of the paper's own DOI usually does).
  2. If no DOI was found in the text, or the one found doesn't actually
     resolve, fall back to a Crossref bibliographic search by title --
     only trusted if the top result's own title is a close match to
     what was searched for, since a free-text search is far less
     precise than a direct DOI lookup.

If BOTH of those fail, a third fallback kicks in: a general web search
(Brave, then SerpApi) plus LLM extraction, the same approach
lookup_bibliography.py already uses for books. This matters for a real,
common case Crossref structurally can't help with: Crossref is a
journal-article/conference-paper registry, and this corpus' "papers"
genuinely include things that were never going to be in it regardless
of how the title search is worded -- industry reports, white papers,
AI incident database entries, any professionally published but
non-DOI'd technical document. Results from this path are recorded with
bibliography_source="web_search" (not "doi_lookup") and a
lookup_confidence, the same honest provenance distinction
lookup_bibliography.py already makes for books -- a much better
starting point than a filename guess, but explicitly less rigorous
than an actual resolved DOI, and worth a glance before fully trusting.

Either way a DOI IS found, it's only trusted once Crossref actually
resolves it -- unlike ISBN, a DOI has no checksum to validate offline;
resolving it against the real registry IS the validation step.

Never touches a paper already marked bibliography_verified=True, and
(by default) skips one already bibliography_source in ("doi_lookup",
"web_search") too, unless --force is passed.

Usage:
    python -m app.cli lookup-paper-doi
    python -m app.cli lookup-paper-doi --force
"""

import json
import re
import time

import requests
from openai import OpenAI
from pypdf import PdfReader

from app.config import PAPER_PDF_DIR, CROSSREF_MAILTO, BRAVE_API_KEY, SERPAPI_API_KEY, DEFAULT_CHAT_MODEL
from app.db.session import get_session
from app.models.paper import Paper
from app.logging_config import get_logger

logger = get_logger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPAPI_SEARCH_URL = "https://serpapi.com/search"

# Tried first: a DOI immediately preceded by a "doi:" or "doi.org/"
# label, much more likely to be the paper's own DOI than a bare match.
LABELED_DOI_RE = re.compile(r"(?:doi\.org/|doi:?\s*)(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", re.IGNORECASE)
BARE_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b")

TRAILING_PUNCT = ".,;:)]}'\""


def clean_doi_candidate(raw: str) -> str:
    return raw.rstrip(TRAILING_PUNCT)


def find_doi_in_text(text: str) -> str | None:
    labeled = LABELED_DOI_RE.search(text)
    if labeled:
        return clean_doi_candidate(labeled.group(1))
    bare = BARE_DOI_RE.search(text)
    if bare:
        return clean_doi_candidate(bare.group(1))
    return None


def find_doi_in_pdf(pdf_path, max_pages: int = 2) -> str | None:
    """Only scans the first couple of pages on purpose -- a paper's own
    DOI is almost always there (title page / running header), while its
    reference list, which would also be full of DOI-shaped strings
    belonging to OTHER papers, doesn't start until later."""
    try:
        reader = PdfReader(str(pdf_path))
        for i in range(min(max_pages, len(reader.pages))):
            text = reader.pages[i].extract_text() or ""
            doi = find_doi_in_text(text)
            if doi:
                return doi
    except Exception as e:
        logger.warning("Could not read %s while looking for a DOI: %s", pdf_path.name, e)
    return None


def format_authors(crossref_authors) -> str | None:
    if not crossref_authors:
        return None
    parts = []
    for a in crossref_authors:
        family = a.get("family")
        given = a.get("given")
        if not family:
            continue
        parts.append(f"{family}, {given[0]}." if given else family)
    return "; ".join(parts) or None


def extract_year(record: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        date_parts = (record.get(key) or {}).get("date-parts")
        if date_parts and date_parts[0] and date_parts[0][0]:
            return int(date_parts[0][0])
    return None


def titles_roughly_match(a: str, b: str) -> bool:
    """Conservative similarity, not exact equality -- whitespace,
    punctuation and casing vary too much for that. Real enough to reject
    a search result that's clearly a different paper entirely, which
    matters here since a bibliographic search has no unique identifier
    to lean on the way a direct DOI lookup does."""
    normalize = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
    a_words = set(normalize(a).split())
    b_words = set(normalize(b).split())
    if not a_words or not b_words:
        return False
    overlap = len(a_words & b_words) / len(a_words | b_words)
    return overlap >= 0.6


def crossref_lookup_by_doi(doi: str) -> dict | None:
    try:
        params = {"mailto": CROSSREF_MAILTO} if CROSSREF_MAILTO else {}
        response = requests.get(f"{CROSSREF_WORKS_URL}/{doi}", params=params, timeout=15)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("message")
    except requests.RequestException as e:
        logger.warning("Crossref lookup failed for DOI %s: %s", doi, e)
        return None


def crossref_search_by_title(title: str) -> dict | None:
    try:
        params = {"query.bibliographic": title, "rows": 1}
        if CROSSREF_MAILTO:
            params["mailto"] = CROSSREF_MAILTO
        response = requests.get(CROSSREF_WORKS_URL, params=params, timeout=15)
        response.raise_for_status()
        items = (response.json().get("message") or {}).get("items", [])
        if not items:
            return None
        candidate = items[0]
        candidate_title = (candidate.get("title") or [""])[0]
        if not titles_roughly_match(title, candidate_title):
            logger.info("Top Crossref result %r doesn't look like a match for %r -- skipping",
                        candidate_title, title)
            return None
        return candidate
    except requests.RequestException as e:
        logger.warning("Crossref title search failed for %r: %s", title, e)
        return None


def search_brave(query: str, count: int = 5) -> list:
    """Mirrors lookup_bibliography.py's own search_brave exactly in
    shape and behavior -- not imported from there, to keep these two
    independent CLI commands from depending on each other for
    something this small, but identical in what it returns."""
    if not BRAVE_API_KEY:
        return []
    try:
        response = requests.get(
            BRAVE_SEARCH_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": BRAVE_API_KEY},
            params={"q": query, "count": count},
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("web", {}).get("results", [])
    except requests.RequestException as e:
        logger.warning("Brave search failed for %r: %s", query, e)
        return []


def search_serpapi(query: str, count: int = 5) -> list:
    """Fallback for when Brave fails or comes back empty. Normalized
    to the same title/url/description shape search_brave() produces --
    SerpApi's own field names are link/snippet, not url/description."""
    if not SERPAPI_API_KEY:
        return []
    try:
        response = requests.get(
            SERPAPI_SEARCH_URL,
            params={"engine": "google", "q": query, "num": count, "api_key": SERPAPI_API_KEY},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("SerpApi search failed for %r: %s", query, e)
        return []
    organic_results = response.json().get("organic_results", [])
    return [
        {"title": r.get("title", ""), "url": r.get("link", ""), "description": r.get("snippet", "")}
        for r in organic_results
    ]


def search_with_fallback(query: str, count: int = 5) -> list:
    """Brave first, SerpApi only if Brave raised or came back with
    nothing -- keeps this at one paid search call in the normal case,
    the fallback only spending a second one when the first genuinely
    didn't help."""
    results = search_brave(query, count=count)
    if results:
        return results
    return search_serpapi(query, count=count)


def extract_paper_bibliography_from_web(openai_client, title_hint: str, search_results: list,
                                         model: str = DEFAULT_CHAT_MODEL) -> dict:
    """The actual fallback for papers Crossref was never going to have
    -- industry reports, white papers, AI incident database entries,
    any professionally published technical document without a DOI.
    Same web-search-and-LLM-extract approach lookup_bibliography.py
    already uses for books, adapted to a paper's own fields (venue and
    abstract instead of publisher and edition)."""
    if not search_results:
        return {}

    context = "\n\n".join(
        f"Title: {r.get('title', '')}\nURL: {r.get('url', '')}\nSnippet: {r.get('description', '')}"
        for r in search_results
    )
    system_prompt = (
        "You extract bibliographic data about a specific paper, report, or technical "
        "document from web search results. The source might be a journal article, "
        "conference paper, industry report, white paper, or any other professionally "
        "published technical document -- not every real source has a DOI. Respond with "
        "ONLY a JSON object with these exact keys: title, authors, year, venue, abstract, "
        "confidence. authors should be semicolon-separated 'Surname, F.' entries, or the "
        "publishing organization's name if there's no individual author (e.g. an "
        "institutional report). venue is the publishing venue, journal, conference, or "
        "organization -- whatever's most accurate for this kind of source. year is an "
        "integer or null. abstract is a short summary if one is available in the search "
        "results, else null. confidence is \"high\", \"medium\", or \"low\" based on how "
        "consistent the search results are with each other -- if results disagree, seem "
        "thin, or seem to be about a different document, say low rather than guessing. "
        "Use null for any field you can't determine confidently."
    )
    user_prompt = f"Document (from filename, may be imprecise): {title_hint}\n\nSearch results:\n\n{context}"

    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}


def apply_web_result_to_paper(paper: Paper, found: dict) -> None:
    paper.title = found.get("title") or paper.title
    paper.authors = found.get("authors")
    paper.year = found.get("year")
    paper.venue = found.get("venue")
    paper.abstract = found.get("abstract") or paper.abstract
    paper.doi = None  # this path never produces one -- clear any stale value from a previous attempt rather than leave it
    paper.bibliography_source = "web_search"
    paper.lookup_confidence = found.get("confidence", "low")


def apply_record_to_paper(paper: Paper, record: dict, doi: str) -> None:
    title_list = record.get("title") or []
    paper.title = title_list[0] if title_list else paper.title
    paper.authors = format_authors(record.get("author"))
    paper.year = extract_year(record)
    container = record.get("container-title") or []
    paper.venue = container[0] if container else None
    paper.doi = doi
    abstract = record.get("abstract")
    if abstract:
        # Crossref abstracts come wrapped in JATS XML tags (<jats:p>...</jats:p>) -- strip them, keep the text.
        paper.abstract = re.sub(r"<[^>]+>", "", abstract).strip()
    paper.bibliography_source = "doi_lookup"


def main(force: bool = False):
    openai_client = OpenAI() if (BRAVE_API_KEY or SERPAPI_API_KEY) else None

    with get_session() as session:
        query_filter = Paper.bibliography_verified.is_(False)
        if not force:
            query_filter = query_filter & ~Paper.bibliography_source.in_(["doi_lookup", "web_search"])
        paper_ids = [p.id for p in session.query(Paper.id).filter(query_filter).all()]

    if not paper_ids:
        logger.info("Nothing to look up -- every paper is either verified or already "
                    "doi_lookup'd/web_search'd (pass --force to redo those too).")
        return

    for paper_id in paper_ids:
        # Each paper gets its own session/commit boundary, deliberately
        # -- doi is a unique column, and two papers resolving to the same
        # DOI (a duplicate PDF, two versions of one paper, anything) is a
        # real possibility once this runs across a real library. With one
        # shared session for the whole batch, that single conflict would
        # fail at the final commit and roll back every paper already
        # processed in this run, not just the one that collided.
        try:
            with get_session() as session:
                paper = session.get(Paper, paper_id)
                if paper is None:
                    continue

                pdf_path = PAPER_PDF_DIR / f"{paper.source_key}.pdf"
                record = None
                doi = None

                if pdf_path.exists():
                    doi = find_doi_in_pdf(pdf_path)
                    if doi:
                        logger.info("Found DOI %s in %s, resolving against Crossref...", doi, pdf_path.name)
                        record = crossref_lookup_by_doi(doi)
                        if record is None:
                            logger.warning("DOI %s found in %s doesn't actually resolve -- "
                                           "falling back to a title search", doi, pdf_path.name)
                            doi = None

                if record is None:
                    logger.info("Searching Crossref by title for %r...", paper.title)
                    record = crossref_search_by_title(paper.title)
                    if record:
                        doi = record.get("DOI")

                if record is not None:
                    apply_record_to_paper(paper, record, doi)
                    session.add(paper)
                    logger.info("Resolved %s -> doi=%s title=%r year=%s",
                                paper.source_key, paper.doi, paper.title, paper.year)
                    continue

                # Crossref structurally can't help here -- it's a DOI
                # registry, and this paper has neither a discoverable
                # DOI nor a title match in it. That's the expected,
                # normal outcome for a real industry report or white
                # paper, not a failure of the search itself, so this
                # falls back to a general web search rather than giving
                # up on the paper entirely.
                if openai_client is None:
                    logger.warning("Could not resolve a DOI for %s, and no BRAVE_API_KEY/"
                                    "SERPAPI_API_KEY is set to try a web-search fallback", paper.source_key)
                    continue

                logger.info("No DOI resolution for %s -- trying a general web search "
                            "(it may genuinely not have a DOI, e.g. an industry report)", paper.source_key)
                results = search_with_fallback(f"{paper.title} paper OR report")
                found = extract_paper_bibliography_from_web(openai_client, paper.source_key, results)
                if not found or not found.get("title"):
                    logger.warning("Could not resolve a bibliography for %s by any method", paper.source_key)
                    continue

                apply_web_result_to_paper(paper, found)
                session.add(paper)
                logger.info("Resolved %s via web search (%s confidence) -> title=%r year=%s",
                            paper.source_key, paper.lookup_confidence, paper.title, paper.year)
        except Exception as e:
            # Whatever the reason (a duplicate DOI being the realistic
            # one), this paper's update is abandoned and every other
            # paper in the batch is unaffected -- already-committed
            # papers from earlier in this same run stay committed.
            logger.error("Failed to resolve/apply bibliography for paper id=%s: %s", paper_id, e)

        time.sleep(0.5)  # a polite, not-hammering pace between papers

    logger.info("Done. Review papers with bibliography_source='doi_lookup' in /admin -- "
                "set them verified once you've checked one against the real published record.")


if __name__ == "__main__":
    import sys
    main(force="--force" in sys.argv)