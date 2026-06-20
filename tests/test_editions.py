import sys, random, json
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.book import Book
from app.ingestion.seed_books import resolve_preferred_editions

NINTH_KEY = "Software-Engineering-9th-Edition-by-Ian-Sommerville"
FAKE_8TH_KEY = "Software-Engineering-8th-Edition-by-Ian-Sommerville"

# Self-contained: create the 9th-edition row directly if it doesn't
# already exist, rather than depending on an external `seed-books` run
# against the real (copyrighted, never-committed) PDF having already
# populated it -- this needs to work standalone in CI.
with get_session() as session:
    leftover = session.query(Book).filter_by(source_key=FAKE_8TH_KEY).one_or_none()
    if leftover is not None:
        session.delete(leftover)

    if session.query(Book).filter_by(source_key=NINTH_KEY).one_or_none() is None:
        session.add(Book(
            source_key=NINTH_KEY, title="Software Engineering", authors="Sommerville, I.",
            year=2011, publisher="Pearson Education / Addison-Wesley", edition="9th ed.",
            page_mode="labeled", bibliography_verified=True,
        ))

with get_session() as session:
    existing_9th = session.query(Book).filter_by(source_key=NINTH_KEY).one()
    existing_9th.work_key = "sommerville-software-engineering"
    session.add(existing_9th)

    fake_8th = Book(
        source_key=FAKE_8TH_KEY,
        title="Software Engineering",
        authors="Sommerville, I.",
        year=2006,
        publisher="Pearson",
        edition="8th ed.",
        work_key="sommerville-software-engineering",
        page_mode="labeled",
        bibliography_verified=True,
    )
    session.add(fake_8th)
    session.flush()

    resolve_preferred_editions(session)

with get_session() as session:
    ninth = session.query(Book).filter_by(source_key=NINTH_KEY).one()
    eighth = session.query(Book).filter_by(source_key=FAKE_8TH_KEY).one()
    print(f"9th edition (year {ninth.year}): is_preferred_edition = {ninth.is_preferred_edition}")
    print(f"8th edition (year {eighth.year}): is_preferred_edition = {eighth.is_preferred_edition}")
    assert ninth.is_preferred_edition is True
    assert eighth.is_preferred_edition is False

    from app.retrieval.query_engine import get_excluded_source_keys
    excluded = get_excluded_source_keys(session)
    print("\nExcluded by default (non-preferred editions):", excluded)
    assert eighth.source_key in excluded
    assert ninth.source_key not in excluded

# Now test the actual pin behavior: a human verifying+preferring the
# OLDER edition (via /admin, in practice) should stick, not get
# overridden by year on the next resolution run.
with get_session() as session:
    eighth = session.query(Book).filter_by(source_key=FAKE_8TH_KEY).one()
    eighth.is_preferred_edition = True
    eighth.edition_pinned = True
    session.add(eighth)
    session.flush()
    resolve_preferred_editions(session)

with get_session() as session:
    ninth = session.query(Book).filter_by(source_key=NINTH_KEY).one()
    eighth = session.query(Book).filter_by(source_key=FAKE_8TH_KEY).one()
    print(f"\nAfter pinning the 8th edition: ninth.is_preferred_edition={ninth.is_preferred_edition}, "
          f"eighth.is_preferred_edition={eighth.is_preferred_edition}")
    assert eighth.is_preferred_edition is True, "a verified+preferred pin should stick even though it's the older edition"
    assert ninth.is_preferred_edition is False, "the pin should flip every other edition in the group to not-preferred"

# Clean up after ourselves too, so a fresh run right after this one starts
# from the same baseline rather than relying on the next run's cleanup step.
with get_session() as session:
    fake = session.query(Book).filter_by(source_key=FAKE_8TH_KEY).one_or_none()
    if fake is not None:
        session.delete(fake)
    ninth = session.query(Book).filter_by(
        source_key=NINTH_KEY
    ).one_or_none()
    if ninth is not None:
        ninth.work_key = None
        ninth.is_preferred_edition = True
        session.add(ninth)

print("\nAll edition-resolution assertions passed.")
