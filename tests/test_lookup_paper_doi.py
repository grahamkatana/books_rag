import sys
sys.path.insert(0, ".")

from app.ingestion import lookup_paper_doi as lpd
from app.db.session import get_session
from app.models.paper import Paper

# --- pure logic: DOI extraction, formatting, similarity ---

text_with_both = """
This paper is available at https://doi.org/10.1145/3744916.3787811
Some intro text. Elsewhere in the document a different work is cited
as 10.1109/ACCESS.2025.3532853 in the bibliography.
"""
assert lpd.find_doi_in_text(text_with_both) == "10.1145/3744916.3787811", \
    "a labeled DOI must win over a bare one found elsewhere in the same text"

assert lpd.find_doi_in_text("See 10.1371/journal.pone.0033693 for details.") == "10.1371/journal.pone.0033693"
assert lpd.find_doi_in_text("doi: 10.1145/3744916.3787811).") == "10.1145/3744916.3787811", \
    "trailing punctuation should be stripped"
assert lpd.find_doi_in_text("Just a normal sentence with page 10.5 referenced.") is None

assert lpd.format_authors([{"family": "Becker", "given": "F."}, {"family": "Sergeyuk", "given": "A."}]) \
    == "Becker, F.; Sergeyuk, A."
assert lpd.format_authors([{"family": "NoGivenName"}]) == "NoGivenName"
assert lpd.format_authors([]) is None
assert lpd.format_authors(None) is None

assert lpd.extract_year({"issued": {"date-parts": [[2016, 11]]}}) == 2016
assert lpd.extract_year({"published-print": {"date-parts": [[2022, 3]]}, "issued": {"date-parts": [[2021]]}}) == 2022
assert lpd.extract_year({}) is None

assert lpd.titles_roughly_match("Evolving with AI: A Longitudinal Analysis", "evolving with ai a longitudinal analysis") is True
assert lpd.titles_roughly_match("Evolving with AI", "Completely Unrelated Paper About Frogs") is False
assert lpd.titles_roughly_match("", "anything") is False

print("Pure-logic assertions passed.")

# --- apply_record_to_paper, including JATS abstract-tag stripping ---

class FakePaper:
    title = "placeholder"
    authors = None
    year = None
    venue = None
    doi = None
    abstract = None
    bibliography_source = None

p = FakePaper()
record = {
    "title": ["Evolving with AI: A Longitudinal Analysis of Developer Logs"],
    "author": [{"family": "Becker", "given": "F."}],
    "container-title": ["ICSE 2026"],
    "issued": {"date-parts": [[2026, 4]]},
    "abstract": "<jats:p>This paper presents a <jats:italic>longitudinal</jats:italic> study.</jats:p>",
}
lpd.apply_record_to_paper(p, record, "10.1145/3744916.3787811")
assert p.title == "Evolving with AI: A Longitudinal Analysis of Developer Logs"
assert p.authors == "Becker, F."
assert p.year == 2026
assert p.venue == "ICSE 2026"
assert p.abstract == "This paper presents a longitudinal study.", "JATS tags should be stripped"
assert p.bibliography_source == "doi_lookup"

print("apply_record_to_paper assertions passed.")

# --- full main() flow: skip rules + the duplicate-DOI batch-isolation fix ---

VERIFIED_KEY = "test_paper_doi_already_verified"
AUTO_KEY = "test_paper_doi_already_looked_up"
NEW_KEY = "test_paper_doi_new"

with get_session() as session:
    for key in (VERIFIED_KEY, AUTO_KEY, NEW_KEY):
        existing = session.query(Paper).filter_by(source_key=key).one_or_none()
        if existing is not None:
            session.delete(existing)

with get_session() as session:
    session.add(Paper(source_key=VERIFIED_KEY, title="Already Verified Paper",
                       bibliography_verified=True, bibliography_source="manual"))
    session.add(Paper(source_key=AUTO_KEY, title="Old DOI Lookup Title",
                       bibliography_verified=False, bibliography_source="doi_lookup", doi="10.0000/old"))
    session.add(Paper(source_key=NEW_KEY, title="A New Unverified Paper",
                       bibliography_verified=False, bibliography_source="filename_guess"))

real_record = {
    "DOI": "10.1145/3744916.3787811",
    "title": ["Evolving with AI: A Longitudinal Analysis of Developer Logs"],
    "author": [{"family": "Becker", "given": "F."}],
    "container-title": ["ICSE 2026"],
    "issued": {"date-parts": [[2026, 4]]},
}
lpd.crossref_lookup_by_doi = lambda doi: None
lpd.crossref_search_by_title = lambda title: real_record

try:
    lpd.main(force=False)

    with get_session() as session:
        verified = session.query(Paper).filter_by(source_key=VERIFIED_KEY).one()
        auto = session.query(Paper).filter_by(source_key=AUTO_KEY).one()
        new = session.query(Paper).filter_by(source_key=NEW_KEY).one()
        assert verified.title == "Already Verified Paper"
        assert auto.title == "Old DOI Lookup Title", "already-doi_lookup paper should be skipped without --force"
        assert new.doi == "10.1145/3744916.3787811"
        assert new.bibliography_source == "doi_lookup"

    print("Skip-rules assertions passed.")

    # Now force a redo -- BOTH unverified papers will resolve to the same
    # DOI via the mock, the realistic duplicate-DOI conflict. The paper
    # processed first must keep its successful write; the one that loses
    # the unique-constraint race must be left exactly as it was, and
    # neither outcome should affect the other.
    lpd.main(force=True)

    with get_session() as session:
        new = session.query(Paper).filter_by(source_key=NEW_KEY).one()
        auto = session.query(Paper).filter_by(source_key=AUTO_KEY).one()
        verified = session.query(Paper).filter_by(source_key=VERIFIED_KEY).one()

        assert new.doi == "10.1145/3744916.3787811", "the earlier-processed paper's resolution must survive"
        assert auto.doi == "10.0000/old", "the conflicting paper must be left untouched, not partially updated"
        assert verified.title == "Already Verified Paper", "verified paper must still be untouched even with --force"

    print("Duplicate-DOI batch-isolation assertions passed.")
finally:
    with get_session() as session:
        for key in (VERIFIED_KEY, AUTO_KEY, NEW_KEY):
            row = session.query(Paper).filter_by(source_key=key).one_or_none()
            if row is not None:
                session.delete(row)

print("\nAll lookup_paper_doi assertions passed.")

# --- search_brave / search_serpapi / search_with_fallback: same pattern as lookup_bibliography.py's own ---
from unittest.mock import patch, MagicMock
import requests

print("\n--- search_serpapi: field names normalized to match search_brave exactly ---")
fake_response = MagicMock()
fake_response.raise_for_status = lambda: None
fake_response.json = lambda: {"organic_results": [
    {"title": "An Industry Report", "link": "https://example.com/report", "snippet": "A real report."},
]}
with patch.object(lpd, "SERPAPI_API_KEY", "fake-key"), patch.object(lpd.requests, "get", return_value=fake_response):
    results = lpd.search_serpapi("query")
assert results == [{"title": "An Industry Report", "url": "https://example.com/report", "description": "A real report."}]
print("OK")

print("\n--- search_serpapi: no key set -- empty, no network call ---")
with patch.object(lpd, "SERPAPI_API_KEY", None), patch.object(lpd.requests, "get") as mock_get:
    assert lpd.search_serpapi("query") == []
    assert not mock_get.called
print("OK")

print("\n--- search_with_fallback: Brave succeeds -- SerpApi never attempted ---")
with patch.object(lpd, "search_brave", return_value=[{"title": "x", "url": "y", "description": "z"}]), \
     patch.object(lpd, "search_serpapi") as mock_serp:
    results2 = lpd.search_with_fallback("query")
assert results2 == [{"title": "x", "url": "y", "description": "z"}]
assert not mock_serp.called
print("OK")

print("\n--- search_with_fallback: Brave empty -- falls back to SerpApi ---")
with patch.object(lpd, "search_brave", return_value=[]), \
     patch.object(lpd, "search_serpapi", return_value=[{"title": "fb", "url": "u", "description": "d"}]):
    results3 = lpd.search_with_fallback("query")
assert len(results3) == 1
print("OK")

# --- the actual point of this whole change: Crossref fails entirely -> web search resolves it ---
print("\n--- main(): when Crossref has nothing at all, falls back to web search + LLM extraction ---")
WEB_KEY = "test_web_fallback_paper"
with get_session() as session:
    existing = session.query(Paper).filter_by(source_key=WEB_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)
with get_session() as session:
    session.add(Paper(source_key=WEB_KEY, title="Some Industry Report", bibliography_source="filename_guess"))

web_found = {
    "title": "The Real Industry Report Title", "authors": "Acme Research Org",
    "year": 2025, "venue": "Acme Research Org", "abstract": "A summary.", "confidence": "medium",
}

with patch.object(lpd, "crossref_lookup_by_doi", return_value=None), \
     patch.object(lpd, "crossref_search_by_title", return_value=None), \
     patch.object(lpd, "search_with_fallback", return_value=[{"title": "x", "url": "y", "description": "z"}]), \
     patch.object(lpd, "extract_paper_bibliography_from_web", return_value=web_found), \
     patch.object(lpd, "OpenAI", return_value=MagicMock()), \
     patch.object(lpd, "BRAVE_API_KEY", "fake-key"):
    lpd.main(force=True)

with get_session() as session:
    paper = session.query(Paper).filter_by(source_key=WEB_KEY).one()
    assert paper.title == "The Real Industry Report Title"
    assert paper.bibliography_source == "web_search"
    assert paper.lookup_confidence == "medium"
    assert paper.doi is None
    assert paper.venue == "Acme Research Org"
    session.delete(paper)
print("OK")

print("\n--- main(): --force without it now also skips already-web_search'd rows ---")
with get_session() as session:
    existing = session.query(Paper).filter_by(source_key=WEB_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)
with get_session() as session:
    session.add(Paper(source_key=WEB_KEY, title="Old Web Search Title", bibliography_source="web_search"))

extraction_called = {"value": False}
def track_extraction(*args, **kwargs):
    extraction_called["value"] = True
    return {}

with patch.object(lpd, "crossref_lookup_by_doi", return_value=None), \
     patch.object(lpd, "crossref_search_by_title", return_value=None), \
     patch.object(lpd, "extract_paper_bibliography_from_web", side_effect=track_extraction), \
     patch.object(lpd, "OpenAI", return_value=MagicMock()), \
     patch.object(lpd, "BRAVE_API_KEY", "fake-key"):
    lpd.main(force=False)

assert extraction_called["value"] is False, "an already-web_search'd row must be skipped without --force"
with get_session() as session:
    paper = session.query(Paper).filter_by(source_key=WEB_KEY).one()
    assert paper.title == "Old Web Search Title"
    session.delete(paper)
print("OK")

print("\n--- main(): no API keys at all -- skips the web-search fallback cleanly, no crash ---")
with get_session() as session:
    existing = session.query(Paper).filter_by(source_key=WEB_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)
with get_session() as session:
    session.add(Paper(source_key=WEB_KEY, title="No Keys Paper", bibliography_source="filename_guess"))

with patch.object(lpd, "crossref_lookup_by_doi", return_value=None), \
     patch.object(lpd, "crossref_search_by_title", return_value=None), \
     patch.object(lpd, "BRAVE_API_KEY", None), \
     patch.object(lpd, "SERPAPI_API_KEY", None):
    lpd.main(force=True)  # must not raise

with get_session() as session:
    paper = session.query(Paper).filter_by(source_key=WEB_KEY).one()
    assert paper.title == "No Keys Paper", "nothing should change when no fallback is even possible"
    session.delete(paper)
print("OK")

print("\nAll web-search-fallback assertions passed.")