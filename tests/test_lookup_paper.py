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