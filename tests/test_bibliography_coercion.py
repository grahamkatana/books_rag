import sys, json
sys.path.insert(0, ".")

import app.ingestion.lookup_bibliography as lb
from app.db.session import get_session
from app.models.book import Book

lb.BRAVE_API_KEY = "fake-key-for-testing"

BOOK_KEY = "test_coercion_book"


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


with get_session() as session:
    existing = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if existing is not None:
        session.delete(existing)

with get_session() as session:
    session.add(Book(source_key=BOOK_KEY, title="Placeholder", bibliography_verified=False,
                      bibliography_source="filename_guess"))

# Reproduce the exact reported bug: authors as a JSON array, like an LLM
# extracting a book with several named authors (e.g. CLRS's four) might
# plausibly produce despite the prompt asking for one joined string --
# plus a couple of other plausible type mismatches at once.
lb.search_brave = lambda query, count=5: [{"title": "fake result", "url": "x", "description": "fake"}]
lb.OpenAI = lambda: FakeOpenAIClient({
    "title": "A Synthetic Book For Testing",
    "authors": ["Cormen, T.", "Leiserson, C.", "Rivest, R.", "Stein, C."],
    "year": "2011",  # year as a string, another plausible LLM quirk
    "is_editor": ["false"],  # list-wrapped string -- bool(["false"]) would be True, a silent correctness bug
    "publisher": "MIT Press",
    "edition": "4th ed.",
    "confidence": "high",
})

try:
    lb.main(force=False)  # should NOT crash

    with get_session() as session:
        book = session.query(Book).filter_by(source_key=BOOK_KEY).one()
        print("authors (coerced):", repr(book.authors))
        print("year (coerced):", repr(book.year))
        print("is_editor (coerced):", repr(book.is_editor))
        assert isinstance(book.authors, str)
        assert book.authors == "Cormen, T., Leiserson, C., Rivest, R., Stein, C."
        assert book.year == 2011
        assert book.is_editor is False, "list-wrapped 'false' string should coerce to actual False, not True"

    print("\nList-bug regression test passed -- lookup-bibliography no longer crashes on this input.")
finally:
    with get_session() as session:
        row = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
        if row is not None:
            session.delete(row)
