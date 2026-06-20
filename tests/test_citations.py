import sys
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.book import Book
from app.retrieval.citations import render_citation, full_apa_reference, extract_citation_tags

# Inject the same real, copyright-page-verified bibliographic data used
# elsewhere in this project (see seed_books.default_overrides()) directly,
# rather than depending on an external `seed-books` run against real PDF
# files having already populated these rows. Real book PDFs aren't (and
# shouldn't be) committed to this repo, so this test needs to be
# self-contained to run in CI -- this also makes it a better test
# generally, since it no longer silently depends on unrelated setup steps
# having been run first.
FIXTURES = {
    "Software-Engineering-9th-Edition-by-Ian-Sommerville": dict(
        title="Software Engineering", authors="Sommerville, I.", is_editor=False,
        year=2011, publisher="Pearson Education / Addison-Wesley", edition="9th ed.",
        page_mode="labeled", bibliography_verified=True,
    ),
    "The-Gale-Encyclopedia-of-Medicine-3rd-Edition-staibabussalamsula_ac__id_": dict(
        title="The Gale Encyclopedia of Medicine", authors="Longe, J. L.", is_editor=True,
        year=2006, publisher="Thomson Gale", edition="3rd ed.",
        page_mode="labeled", bibliography_verified=True,
    ),
    "_OceanofPDF_com_Risk-First_Software_Development_2E_-_Rob_Moffat": dict(
        title="Risk-First Software Development", authors="Moffat, R.", is_editor=False,
        year=2026, publisher="The Pragmatic Programmers, LLC", edition="2nd ed.",
        page_mode="approximate", bibliography_verified=True,
    ),
}

with get_session() as session:
    for source_key, fields in FIXTURES.items():
        book = session.query(Book).filter_by(source_key=source_key).one_or_none()
        if book is None:
            book = Book(source_key=source_key, **fields)
            session.add(book)
        else:
            for k, v in fields.items():
                setattr(book, k, v)

with get_session() as session:
    sommerville = session.query(Book).filter_by(source_key="Software-Engineering-9th-Edition-by-Ian-Sommerville").one()
    gale = session.query(Book).filter_by(source_key="The-Gale-Encyclopedia-of-Medicine-3rd-Edition-staibabussalamsula_ac__id_").one()
    riskfirst = session.query(Book).filter_by(source_key="_OceanofPDF_com_Risk-First_Software_Development_2E_-_Rob_Moffat").one()

    print("--- in-text citations ---")
    c1 = render_citation({"printed_page": "46-47", "source": sommerville.source_key}, sommerville)
    print(" Sommerville (page-cited):", c1.apa_text)
    print("   tagged:", c1.tagged)

    c2 = render_citation({"printed_page": "1", "source": gale.source_key}, gale)
    print(" Gale (page-cited, editor):", c2.apa_text)

    c3 = render_citation(
        {"chapter": "Positioning Risk-First Software Development", "physical_page_approx": 17, "source": riskfirst.source_key},
        riskfirst,
    )
    print(" Risk-First (chapter-cited, no real page):", c3.apa_text)
    print("   tagged:", c3.tagged)

    c4 = render_citation({"source": "some_unseeded_book"}, None)
    print(" Unknown/unseeded book fallback:", c4.apa_text)

    print("\n--- full APA reference list entries ---")
    print(" Sommerville:", full_apa_reference(sommerville))
    print(" Gale (editor):", full_apa_reference(gale))
    print(" Risk-First:", full_apa_reference(riskfirst))

    print("\n--- tag extraction round trip ---")
    fake_answer = (
        f"Software is often delivered iteratively {c1.tagged}. "
        f"Reference works like this one are organized alphabetically {c2.tagged}. "
        f"Risk-First reframes development around risk management {c3.tagged}."
    )
    extracted = extract_citation_tags(fake_answer)
    print(" extracted", len(extracted), "tags:")
    for e in extracted:
        print("  ", e)
