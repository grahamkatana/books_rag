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

Either way, a DOI is only trusted once Crossref actually resolves it --
unlike ISBN, a DOI has no checksum to validate offline; resolving it
against the real registry IS the validation step.

Never touches a paper already marked bibliography_verified=True, and
(by default) skips one already bibliography_source="doi_lookup" too,
unless --force is passed.

Usage:
    python -m app.cli lookup-paper-doi
    python -m app.cli lookup-paper-doi --force
"""

import re
import time

import requests
from pypdf import PdfReader

from app.config import PAPER_PDF_DIR, CROSSREF_MAILTO
from app.db.session import get_session
from app.models.paper import Paper
from app.logging_config import get_logger

logger = get_logger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"

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
    with get_session() as session:
        query_filter = Paper.bibliography_verified.is_(False)
        if not force:
            query_filter = query_filter & (Paper.bibliography_source != "doi_lookup")
        paper_ids = [p.id for p in session.query(Paper.id).filter(query_filter).all()]

    if not paper_ids:
        logger.info("Nothing to look up -- every paper is either verified or "
                    "already doi_lookup'd (pass --force to redo those too).")
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

                if record is None:
                    logger.warning("Could not resolve a DOI for %s", paper.source_key)
                    continue

                apply_record_to_paper(paper, record, doi)
                session.add(paper)
                logger.info("Resolved %s -> doi=%s title=%r year=%s",
                            paper.source_key, paper.doi, paper.title, paper.year)
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