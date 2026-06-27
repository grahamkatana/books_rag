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

    # --- search_serpapi / search_with_fallback: every outcome must be
    # explicitly visible in the logs, not just inferred from behavior.
    # This is the literal fix for "no clue if SerpApi has been
    # triggered or not" -- each branch below confirms the right log
    # call actually fires, by patching the logger itself and checking
    # what it was called with, not just the function's return value.
    from unittest.mock import patch, MagicMock
    import requests

    print("\n--- search_serpapi: no key set -- logs that it was skipped, never calls requests.get ---")
    with patch.object(lb, "SERPAPI_API_KEY", None), \
         patch.object(lb, "logger") as mock_logger, \
         patch.object(lb.requests, "get") as mock_get:
        result = lb.search_serpapi("a query")
    assert result == []
    assert not mock_get.called
    assert mock_logger.info.called
    assert "skipped" in mock_logger.info.call_args[0][0]
    print("OK")

    print("\n--- search_serpapi: request fails -- logs a warning, not silence ---")
    with patch.object(lb, "SERPAPI_API_KEY", "fake-key"), \
         patch.object(lb, "logger") as mock_logger2, \
         patch.object(lb.requests, "get", side_effect=requests.RequestException("boom")):
        result2 = lb.search_serpapi("a query")
    assert result2 == []
    assert mock_logger2.warning.called
    print("OK")

    print("\n--- search_serpapi: empty results -- logs that it found nothing, distinctly from a failure ---")
    fake_empty_response = MagicMock()
    fake_empty_response.raise_for_status = lambda: None
    fake_empty_response.json = lambda: {"organic_results": []}
    with patch.object(lb, "SERPAPI_API_KEY", "fake-key"), \
         patch.object(lb, "logger") as mock_logger3, \
         patch.object(lb.requests, "get", return_value=fake_empty_response):
        result3 = lb.search_serpapi("a query")
    assert result3 == []
    assert mock_logger3.info.called
    assert "zero results" in mock_logger3.info.call_args[0][0]
    print("OK")

    print("\n--- search_serpapi: genuine success -- logs how many results, confirming the fallback DID run ---")
    fake_response = MagicMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"organic_results": [
        {"title": "A Result", "link": "https://example.com", "snippet": "text"},
    ]}
    with patch.object(lb, "SERPAPI_API_KEY", "fake-key"), \
         patch.object(lb, "logger") as mock_logger4, \
         patch.object(lb.requests, "get", return_value=fake_response):
        result4 = lb.search_serpapi("a query")
    assert len(result4) == 1
    assert result4[0] == {"title": "A Result", "url": "https://example.com", "description": "text"}
    assert mock_logger4.info.called
    logged_template, logged_count = mock_logger4.info.call_args[0][0], mock_logger4.info.call_args[0][1]
    assert "result" in logged_template and logged_count == 1
    print("OK")

    print("\n--- search_with_fallback: Brave succeeds -- SerpApi never even attempted, no log about it ---")
    with patch.object(lb, "search_brave", return_value=[{"title": "x", "url": "y", "description": "z"}]), \
         patch.object(lb, "search_serpapi") as mock_serp:
        result5 = lb.search_with_fallback("a query")
    assert result5 == [{"title": "x", "url": "y", "description": "z"}]
    assert not mock_serp.called
    print("OK")

    print("\n--- search_with_fallback: Brave fails with a real HTTPError (e.g. 402) -- falls through to SerpApi ---")
    with patch.object(lb, "logger") as mock_logger5, \
         patch.object(lb, "search_brave", side_effect=requests.HTTPError("402 Client Error: Payment Required")), \
         patch.object(lb, "search_serpapi", return_value=[{"title": "fallback", "url": "u", "description": "d"}]) as mock_serp2:
        result6 = lb.search_with_fallback("a query")
    assert result6 == [{"title": "fallback", "url": "u", "description": "d"}]
    assert mock_serp2.called, "a 402 from Brave must fall through to SerpApi, not just give up"
    assert mock_logger5.warning.called
    print("OK")

    print("\nAll SerpApi fallback visibility assertions passed.")
finally:
    with get_session() as session:
        for key in (VERIFIED_KEY, AUTO_KEY, NEW_KEY):
            row = session.query(Book).filter_by(source_key=key).one_or_none()
            if row is not None:
                session.delete(row)