import sys, json
sys.path.insert(0, ".")

import app.ingestion.lookup_bibliography as lb
from app.db.session import get_session
from app.models.book import Book

# Force the no-key guard off for this test, since we're mocking the HTTP
# call itself rather than testing real network access
lb.BRAVE_API_KEY = "fake-key-for-testing"


class FakeChoiceMessage:
    def __init__(self, content):
        self.content = content

class FakeChoice:
    def __init__(self, content):
        self.message = FakeChoiceMessage(content)

class FakeChatResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeOpenAIClient:
    def __init__(self, canned_json):
        self.canned_json = canned_json
        outer = self

        class _Chat:
            class completions:
                @staticmethod
                def create(model, messages, response_format=None):
                    return FakeChatResponse(json.dumps(outer.canned_json))

        self.chat = _Chat()


fake_results = [
    {"title": "Software Engineering by Ian Sommerville - Pearson", "url": "https://example.com",
     "description": "9th edition, published 2011 by Addison-Wesley/Pearson."},
]

# --- unit test: extract_bibliography directly ---
fake_client = FakeOpenAIClient({
    "title": "Software Engineering", "authors": "Sommerville, I.", "year": 2011,
    "publisher": "Pearson", "edition": "9th ed.", "is_editor": False, "confidence": "high",
})
result = lb.extract_bibliography(fake_client, "some-filename-stem", fake_results)
print("extract_bibliography result:", result)
assert result["title"] == "Software Engineering"
assert result["confidence"] == "high"

empty_result = lb.extract_bibliography(fake_client, "stem", [])
assert empty_result == {}, "no search results should short-circuit to {}"

# --- full main() flow against real Book rows ---
VERIFIED_KEY = "test_lookup_already_verified_book"
AUTO_KEY = "test_lookup_already_auto_looked_up_book"
NEW_KEY = "test_lookup_brand_new_book"

with get_session() as session:
    for key in (VERIFIED_KEY, AUTO_KEY, NEW_KEY):
        existing = session.query(Book).filter_by(source_key=key).one_or_none()
        if existing is not None:
            session.delete(existing)

with get_session() as session:
    session.add(Book(source_key=VERIFIED_KEY, title="Real Verified Title",
                      bibliography_verified=True, bibliography_source="manual"))
    session.add(Book(source_key=AUTO_KEY, title="Old Auto Title",
                      bibliography_verified=False, bibliography_source="auto_lookup",
                      lookup_confidence="low"))
    session.add(Book(source_key=NEW_KEY, title="Brand New Book Title",
                      bibliography_verified=False, bibliography_source="filename_guess"))

lb.search_brave = lambda query, count=5: fake_results
lb.OpenAI = lambda: FakeOpenAIClient({
    "title": "Brand New Book Title (Looked Up)", "authors": "Newauthor, A.", "year": 2023,
    "publisher": "Some Press", "edition": None, "is_editor": False, "confidence": "medium",
})

try:
    lb.main(force=False)

    with get_session() as session:
        verified = session.query(Book).filter_by(source_key=VERIFIED_KEY).one()
        auto = session.query(Book).filter_by(source_key=AUTO_KEY).one()
        new = session.query(Book).filter_by(source_key=NEW_KEY).one()

        assert verified.title == "Real Verified Title", "already-verified book must be untouched"
        assert auto.title == "Old Auto Title", "already-auto-looked-up book should be skipped without --force"
        assert new.title == "Brand New Book Title (Looked Up)"
        assert new.bibliography_verified is False
        assert new.bibliography_source == "auto_lookup"
        assert new.lookup_confidence == "medium"

    print("\n--- now with --force: the already-auto-looked-up book should be redone too ---")
    lb.main(force=True)

    with get_session() as session:
        auto = session.query(Book).filter_by(source_key=AUTO_KEY).one()
        assert auto.title == "Brand New Book Title (Looked Up)", "force should redo even an already-auto-looked-up book"
        verified = session.query(Book).filter_by(source_key=VERIFIED_KEY).one()
        assert verified.title == "Real Verified Title", "verified book must STILL be untouched even with --force"

    print("\nAll lookup_bibliography assertions passed.")
finally:
    with get_session() as session:
        for key in (VERIFIED_KEY, AUTO_KEY, NEW_KEY):
            row = session.query(Book).filter_by(source_key=key).one_or_none()
            if row is not None:
                session.delete(row)
