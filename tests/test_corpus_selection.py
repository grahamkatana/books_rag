import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION, PAPERS_QDRANT_COLLECTION
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.chat import Chat
from app.retrieval.query_engine import answer_question, search_chunks


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector


class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]


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
    class embeddings:
        @staticmethod
        def create(model, input):
            vectors = [[random.random() for _ in range(EMBEDDING_DIM)] for _ in input]
            return FakeEmbeddingResponse(vectors)

    class chat:
        class completions:
            @staticmethod
            def create(model, messages):
                import re
                user_msg = messages[1]["content"]
                tags = re.findall(r"<CITATION>.*?</CITATION>", user_msg)
                body = "".join(f" claim {i}{tag}" for i, tag in enumerate(tags))
                return FakeChatResponse(body.strip() or "no citations available")


BOOK_KEY = "test_corpus_book"
PAPER_KEY = "test_corpus_paper"

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
        existing = session.query(cls).filter_by(source_key=key).one_or_none()
        if existing is not None:
            session.delete(existing)

with get_session() as session:
    session.add(Book(source_key=BOOK_KEY, title="Test Corpus Book", year=2020,
                      bibliography_verified=True, page_mode="labeled"))
    session.add(Paper(source_key=PAPER_KEY, title="Test Corpus Paper", year=2026, authors="Author, A."))

qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
qdrant.create_collection(PAPERS_QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

book_chunk = {"chunk_id": f"{BOOK_KEY}::0", "source": BOOK_KEY, "text": "Book chunk text.", "printed_page": "10"}
paper_chunk = {"chunk_id": f"{PAPER_KEY}::0", "source": PAPER_KEY, "text": "Paper chunk text.", "printed_page": "3"}

qdrant.upsert(collection_name=QDRANT_COLLECTION,
              points=[PointStruct(id=1, vector=[random.random() for _ in range(EMBEDDING_DIM)], payload=book_chunk)])
qdrant.upsert(collection_name=PAPERS_QDRANT_COLLECTION,
              points=[PointStruct(id=1, vector=[random.random() for _ in range(EMBEDDING_DIM)], payload=paper_chunk)])

query_vector = [random.random() for _ in range(EMBEDDING_DIM)]

print("=== corpus='books' (default): must only ever see the book chunk ===")
hits = search_chunks(qdrant, query_vector, top_k=5, corpus="books")
assert len(hits) == 1
assert hits[0].payload["source"] == BOOK_KEY
assert hits[0].payload["_corpus"] == "books"
print("OK")

print("\n=== corpus='papers': must only ever see the paper chunk ===")
hits = search_chunks(qdrant, query_vector, top_k=5, corpus="papers")
assert len(hits) == 1
assert hits[0].payload["source"] == PAPER_KEY
assert hits[0].payload["_corpus"] == "papers"
print("OK")

print("\n=== corpus='both': must see BOTH, correctly tagged, merged by score ===")
hits = search_chunks(qdrant, query_vector, top_k=5, corpus="both")
assert len(hits) == 2
sources_seen = {h.payload["source"] for h in hits}
assert sources_seen == {BOOK_KEY, PAPER_KEY}
corpora_seen = {h.payload["source"]: h.payload["_corpus"] for h in hits}
assert corpora_seen[BOOK_KEY] == "books"
assert corpora_seen[PAPER_KEY] == "papers"
# scores must be in descending order after the merge
assert hits[0].score >= hits[1].score
print("OK")

print("\n=== corpus='both', top_k=1: merge must actually truncate, not just concatenate ===")
hits = search_chunks(qdrant, query_vector, top_k=1, corpus="both")
assert len(hits) == 1, f"expected exactly 1 after truncation, got {len(hits)}"
print("OK")

print("\n=== full answer_question() flow, corpus='both': citations resolve to the right model, paper_id actually persists ===")
fake_openai = FakeOpenAIClient()
with get_session() as session:
    result = answer_question(session, fake_openai, qdrant,
                              question="What does the corpus say?", top_k=5, corpus="both")
    print("citations:", result["citations"])
    assert len(result["citations"]) == 2

    book_citation = next(c for c in result["citations"] if c["book_id"] is not None)
    paper_citation = next(c for c in result["citations"] if c["paper_id"] is not None)
    assert book_citation["paper_id"] is None, "a book citation must never have paper_id set too"
    assert paper_citation["book_id"] is None, "a paper citation must never have book_id set too"
    chat_id = result["chat_id"]

# Verified in a separate session, after the first one's transaction has
# actually committed (get_session()'s __exit__ commits) -- nesting this
# inside the block above would read uncommitted data from a different
# connection and could legitimately see nothing yet.
with get_session() as verify_session:
    chat = verify_session.get(Chat, chat_id)
    assistant_msg = [m for m in chat.messages if m.role == "assistant"][0]
    for c in assistant_msg.citations:
        if c.paper_id is not None:
            assert c.paper.title == "Test Corpus Paper"
            assert c.book is None
        elif c.book_id is not None:
            assert c.book.title == "Test Corpus Book"
            assert c.paper is None

print("OK -- mixed book/paper citations resolved correctly and persisted with the right FK set.")

print("\nAll corpus-selection assertions passed.")

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)