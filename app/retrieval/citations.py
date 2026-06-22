"""
APA-style in-text citation formatting, plus the <CITATION> tag wrapping
the frontend can parse out of an answer.

A citation here is always built from two things: a source -- a Book or
a Paper, bibliographic identity, who/when/what -- and a locator, where
in that source: a page number (books with real page labels, or most
paper chunks via Docling's own page provenance), a chapter/section name
with an approximate page (untrusted books), or just a section name (a
paper chunk Docling couldn't anchor to a specific page at all).
"""

import re
from dataclasses import dataclass

from app.models.book import Book
from app.models.paper import Paper

CITATION_TAG_RE = re.compile(r"<CITATION>(.*?)</CITATION>", re.DOTALL)


@dataclass
class RenderedCitation:
    apa_text: str        # e.g. '(Sommerville, 2011, p. 47)' or '(Becker et al., 2026, p. 12)'
    locator: str | None  # e.g. 'p. 47' or 'Stage 1: Specification' or '"Related Work" section'
    book: Book | None
    paper: Paper | None
    tagged: str           # apa_text wrapped in <CITATION></CITATION>


def build_locator(chunk_payload: dict) -> str | None:
    """Derives the human locator string from a chunk's metadata,
    regardless of which pipeline produced it: page-labeled books,
    chapter-based (untrusted) books, or Docling-chunked papers."""
    if chunk_payload.get("printed_page"):
        return f"p. {chunk_payload['printed_page']}"
    if chunk_payload.get("chapter"):
        page = chunk_payload.get("physical_page_approx")
        if page is not None:
            return f'"{chunk_payload["chapter"]}" section, approx. PDF p.{page}'
        return f'"{chunk_payload["chapter"]}" section'
    if chunk_payload.get("section"):
        # A paper chunk Docling couldn't anchor to a specific page at
        # all -- rare (most chunks do carry real page provenance), but
        # the section heading is still a real, useful locator on its own.
        return f'"{chunk_payload["section"]}" section'
    return None


def author_surname(book: Book) -> str:
    """Extracts just the surname from a full APA author string like
    'Sommerville, I.' for use in an in-text citation, which omits initials."""
    if not book.authors:
        return book.title
    return book.authors.split(",")[0].strip()


def paper_author_citation_label(paper: Paper) -> str:
    """APA's real multi-author in-text rule, which books' single-author-
    biased author_surname() above doesn't need to handle but papers
    routinely do: one author -> surname; two -> "A & B"; three or more
    -> "A et al." paper.authors is semicolon-delimited
    ("Family, F.; Family2, F2."), matching lookup_paper_doi.py's
    format_authors() output exactly."""
    if not paper.authors:
        return paper.title
    surnames = [a.split(",")[0].strip() for a in paper.authors.split(";") if a.strip()]
    if not surnames:
        return paper.title
    if len(surnames) == 1:
        return surnames[0]
    if len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}"
    return f"{surnames[0]} et al."


def format_apa(book: Book | None, locator: str | None, fallback_source: str = "unknown source") -> str:
    """Builds an APA-style parenthetical in-text citation.

    With a known author: (Surname, Year, p. X)
    With no individual author (e.g. an edited reference work): (Title, Year, p. X)
    With nothing verified at all: (source_key, n.d.)
    """
    if book is None:
        return f"({fallback_source}, n.d.)"

    author_or_title = author_surname(book) if book.authors else book.title
    year = str(book.year) if book.year else "n.d."

    if locator:
        return f"({author_or_title}, {year}, {locator})"
    return f"({author_or_title}, {year})"


def format_apa_paper(paper: Paper | None, locator: str | None, fallback_source: str = "unknown source") -> str:
    """Same shape as format_apa(), but using APA's real multi-author
    in-text rule via paper_author_citation_label() instead of always
    taking just the first author -- a paper with five authors should
    read "(Becker et al., 2026, p. 12)", not "(Becker, 2026, p. 12)"."""
    if paper is None:
        return f"({fallback_source}, n.d.)"

    author_or_title = paper_author_citation_label(paper) if paper.authors else paper.title
    year = str(paper.year) if paper.year else "n.d."

    if locator:
        return f"({author_or_title}, {year}, {locator})"
    return f"({author_or_title}, {year})"


def render_citation(chunk_payload: dict, source) -> RenderedCitation:
    """source is a Book, a Paper, or None (unresolved). Dispatches on
    type rather than needing two separate call sites -- query_engine.py
    doesn't need to know in advance which kind of source a given chunk's
    source_key resolved to before calling this."""
    locator = build_locator(chunk_payload)
    fallback = chunk_payload.get("source", "unknown source")

    if isinstance(source, Paper):
        apa_text = format_apa_paper(source, locator, fallback_source=fallback)
        return RenderedCitation(apa_text=apa_text, locator=locator, book=None, paper=source,
                                 tagged=f"<CITATION>{apa_text}</CITATION>")

    apa_text = format_apa(source, locator, fallback_source=fallback)
    return RenderedCitation(apa_text=apa_text, locator=locator, book=source, paper=None,
                             tagged=f"<CITATION>{apa_text}</CITATION>")


def extract_citation_tags(answer_text: str) -> list[str]:
    """Pulls every <CITATION>...</CITATION> payload out of an LLM answer,
    in the order they appear."""
    return CITATION_TAG_RE.findall(answer_text)


def full_apa_reference(book: Book) -> str:
    """Builds a full APA reference-list entry (not an in-text citation) --
    useful for a bibliography view in the frontend. Degrades gracefully
    when fields are missing rather than fabricating them."""
    year = str(book.year) if book.year else "n.d."

    if book.authors:
        author_label = f"{book.authors} (Ed.)" if book.is_editor else book.authors
        author_label = author_label.rstrip(".")
        title_part = book.title
        if book.edition:
            title_part += f" ({book.edition})"
        publisher_part = f" {book.publisher}." if book.publisher else ""
        return f"{author_label}. ({year}). {title_part}.{publisher_part}".strip()

    # No individual author -- treat as an edited/reference work, APA
    # alphabetizes and cites these by title.
    publisher_part = f" {book.publisher}." if book.publisher else ""
    return f"{book.title}. ({year}).{publisher_part}".strip()


def full_apa_reference_paper(paper: Paper) -> str:
    """Full APA reference-list entry for a paper: Author, A., & Author2,
    B. (Year). Title. Venue. https://doi.org/DOI -- same
    degrade-gracefully-on-missing-fields philosophy as
    full_apa_reference() above, never fabricating a field that isn't
    actually known."""
    year = str(paper.year) if paper.year else "n.d."

    if paper.authors:
        # paper.authors is "Family, F.; Family2, F2." -- APA's reference-
        # list format wants "Family, F., & Family2, F2." (ampersand
        # before the last author, comma-separated otherwise), not the
        # semicolon-delimited storage format.
        parts = [a.strip() for a in paper.authors.split(";") if a.strip()]
        if len(parts) == 1:
            author_label = parts[0]
        else:
            author_label = ", ".join(parts[:-1]) + f", & {parts[-1]}"
        author_label = author_label.rstrip(".")  # each stored segment already ends in "." -- avoid a double ".."
        title_part = paper.title
    else:
        author_label = paper.title
        title_part = None

    pieces = [f"{author_label}. ({year})."]
    if title_part:
        pieces.append(f"{title_part}.")
    if paper.venue:
        pieces.append(f"{paper.venue}.")
    if paper.doi:
        pieces.append(f"https://doi.org/{paper.doi}")

    return " ".join(pieces).strip()