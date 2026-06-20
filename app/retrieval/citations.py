"""
APA-style in-text citation formatting, plus the <CITATION> tag wrapping
the frontend can parse out of an answer.

A citation here is always built from two things: a Book (bibliographic
identity -- who/when/what) and a locator (where in that book -- a page
number or a chapter/section name, depending on which chunking pipeline
produced the underlying text).
"""

import re
from dataclasses import dataclass

from app.models.book import Book

CITATION_TAG_RE = re.compile(r"<CITATION>(.*?)</CITATION>", re.DOTALL)


@dataclass
class RenderedCitation:
    apa_text: str       # e.g. '(Sommerville, 2011, p. 47)'
    locator: str | None  # e.g. 'p. 47' or 'Stage 1: Specification'
    book: Book | None
    tagged: str          # apa_text wrapped in <CITATION></CITATION>


def build_locator(chunk_payload: dict) -> str | None:
    """Derives the human locator string from a chunk's metadata, regardless
    of which chunking pipeline (page-labeled vs chapter-based) produced it."""
    if chunk_payload.get("printed_page"):
        return f"p. {chunk_payload['printed_page']}"
    if chunk_payload.get("chapter"):
        page = chunk_payload.get("physical_page_approx")
        if page is not None:
            return f'"{chunk_payload["chapter"]}" section, approx. PDF p.{page}'
        return f'"{chunk_payload["chapter"]}" section'
    return None


def author_surname(book: Book) -> str:
    """Extracts just the surname from a full APA author string like
    'Sommerville, I.' for use in an in-text citation, which omits initials."""
    if not book.authors:
        return book.title
    return book.authors.split(",")[0].strip()


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


def render_citation(chunk_payload: dict, book: Book | None) -> RenderedCitation:
    locator = build_locator(chunk_payload)
    apa_text = format_apa(book, locator, fallback_source=chunk_payload.get("source", "unknown source"))
    return RenderedCitation(
        apa_text=apa_text,
        locator=locator,
        book=book,
        tagged=f"<CITATION>{apa_text}</CITATION>",
    )


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
