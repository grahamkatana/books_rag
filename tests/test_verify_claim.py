import sys, random
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, ".")

import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from pydantic_ai.models.test import TestModel

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION, PAPERS_QDRANT_COLLECTION
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.verification import VerificationDocument, ExtractedClaim
import app.api.clients as clients
import app.agents.verify_claim as vc

BOOK_KEY = "test_verify_claim_regression_book"
PAPER_KEY = "test_verify_claim_regression_paper"

# --- search_web_impl, directly, with a fake RunContext stand-in ---
print("--- search_web_impl ---")
deps = vc.VerificationDeps(all_evidence=[{"source": "corpus", "title": "Existing", "excerpt": "x",
                                          "locator": None, "book_id": 1, "paper_id": None,
                                          "web_url": None, "web_title": None}])
ctx = SimpleNamespace(deps=deps)
with patch.object(vc, "search_brave", return_value=[
    {"title": "Web Result 1", "url": "https://example.com/1", "description": "snippet one"},
]):
    output = vc.search_web_impl(ctx, "test query")
assert len(deps.all_evidence) == 2
assert deps.all_evidence[1]["web_url"] == "https://example.com/1"
assert "[2]" in output, "index must continue from existing evidence count, not restart at 1"

deps_empty = vc.VerificationDeps(all_evidence=[])
with patch.object(vc, "search_brave", return_value=[]):
    output_empty = vc.search_web_impl(SimpleNamespace(deps=deps_empty), "nothing")
assert deps_empty.all_evidence == []
assert "no web results" in output_empty.lower()

deps_fail = vc.VerificationDeps(all_evidence=[])
with patch.object(vc, "search_brave", side_effect=RuntimeError("Brave API down")):
    output_fail = vc.search_web_impl(SimpleNamespace(deps=deps_fail), "fails")
assert deps_fail.all_evidence == []
assert "failed" in output_fail.lower()
print("OK")

# --- gather_corpus_evidence, real in-memory Qdrant + fake embeddings ---
print("\n--- gather_corpus_evidence ---")
with get_session() as session:
    for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)

with get_session() as session:
    session.add(Book(source_key=BOOK_KEY, title="Verify Test Book", year=2020,
                      bibliography_verified=True, page_mode="labeled"))
    session.add(Paper(source_key=PAPER_KEY, title="Verify Test Paper", year=2026))

qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
qdrant.create_collection(PAPERS_QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
qdrant.upsert(collection_name=QDRANT_COLLECTION, points=[
    PointStruct(id=1, vector=[random.random() for _ in range(EMBEDDING_DIM)],
                payload={"source": BOOK_KEY, "text": "Book chunk text.", "printed_page": "10"})
])
qdrant.upsert(collection_name=PAPERS_QDRANT_COLLECTION, points=[
    PointStruct(id=1, vector=[random.random() for _ in range(EMBEDDING_DIM)],
                payload={"source": PAPER_KEY, "text": "Paper chunk text.", "printed_page": "3"})
])


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector


class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]


class FakeOpenAIClient:
    class embeddings:
        @staticmethod
        def create(model, input):
            return FakeEmbeddingResponse([[random.random() for _ in range(EMBEDDING_DIM)] for _ in input])


original_qdrant_client, original_openai_client = clients._qdrant_client, clients._openai_client
clients._qdrant_client = qdrant
clients._openai_client = FakeOpenAIClient()

try:
    evidence = vc.gather_corpus_evidence("Does AI adoption affect skill?", top_k=5)
    assert len(evidence) == 2
    book_ev = next(e for e in evidence if e["book_id"] is not None)
    paper_ev = next(e for e in evidence if e["paper_id"] is not None)
    assert book_ev["title"] == "Verify Test Book" and book_ev["locator"] == "p. 10"
    assert paper_ev["title"] == "Verify Test Paper" and paper_ev["locator"] == "p. 3"
    print("OK")

    # --- verify_claim_text: agent runs against gathered evidence ---
    print("\n--- verify_claim_text ---")
    agent = vc.build_verification_agent()
    original_gather = vc.gather_corpus_evidence
    vc.gather_corpus_evidence = lambda claim_text, top_k=6: [
        {"source": "corpus", "book_id": 5, "paper_id": None, "title": "Some Book",
         "excerpt": "Adoption rose.", "locator": "p. 1", "web_url": None, "web_title": None},
    ]
    try:
        fake_verdict = vc.VerificationVerdict(
            verdict="supported", confidence="high", explanation="Directly confirmed.",
            evidence_cited=[vc.EvidenceCitation(source_index=1, relevance_note="confirms it")],
        )
        with agent.override(model=TestModel(call_tools=[], custom_output_args=fake_verdict.model_dump())):
            verdict, all_evidence = vc.verify_claim_text("Adoption rose significantly.", agent=agent)
        assert verdict.verdict == "supported"
        assert len(all_evidence) == 1
        print("OK")
    finally:
        vc.gather_corpus_evidence = original_gather

    # --- run_verification: full orchestration ---
    print("\n--- run_verification ---")
    with get_session() as session:
        existing = session.query(Book).filter_by(source_key="test_verify_orchestration_book").one_or_none()
        if existing is not None:
            session.delete(existing)

    with get_session() as session:
        real_book = Book(source_key="test_verify_orchestration_book", title="Some Book",
                          bibliography_verified=True, page_mode="labeled")
        session.add(real_book)
        session.flush()
        real_book_id = real_book.id

    good_verdict = vc.VerificationVerdict(
        verdict="supported", confidence="high", explanation="Directly confirmed.",
        evidence_cited=[vc.EvidenceCitation(source_index=1, relevance_note="confirms it")],
    )
    good_evidence = [{"source": "corpus", "book_id": real_book_id, "paper_id": None, "title": "Some Book",
                       "excerpt": "Adoption rose.", "locator": "p. 1", "web_url": None, "web_title": None}]

    with get_session() as session:
        doc = VerificationDocument(filename="test.docx", status="verifying")
        session.add(doc)
        session.flush()
        claim = ExtractedClaim(document_id=doc.id, text="Adoption rose significantly.", order_index=0)
        session.add(claim)
        session.flush()
        claim_id, doc_id = claim.id, doc.id

    original_verify = vc.verify_claim_text
    try:
        vc.verify_claim_text = lambda claim_text, agent=None, top_k=6: (good_verdict, good_evidence)
        assert vc.run_verification(claim_id) is True
        with get_session() as session:
            v = session.get(ExtractedClaim, claim_id).verification
            assert v.verdict == "supported" and v.confidence == "high"
            assert len(v.evidence) == 1
            assert v.evidence[0].book_id == real_book_id
        print("Success path OK")

        bad_verdict = vc.VerificationVerdict(
            verdict="supported", confidence="medium", explanation="test",
            evidence_cited=[vc.EvidenceCitation(source_index=99, relevance_note="bad index")],
        )
        with get_session() as session:
            claim2 = ExtractedClaim(document_id=doc_id, text="Another claim.", order_index=1)
            session.add(claim2)
            session.flush()
            claim2_id = claim2.id
        vc.verify_claim_text = lambda claim_text, agent=None, top_k=6: (bad_verdict, good_evidence)
        assert vc.run_verification(claim2_id) is True, "an out-of-range citation must not fail verification itself"
        with get_session() as session:
            assert len(session.get(ExtractedClaim, claim2_id).verification.evidence) == 0
        print("Out-of-range citation handled OK")

        def raise_error(claim_text, agent=None, top_k=6):
            raise RuntimeError("simulated failure")
        vc.verify_claim_text = raise_error
        with get_session() as session:
            claim3 = ExtractedClaim(document_id=doc_id, text="A third claim.", order_index=2)
            session.add(claim3)
            session.flush()
            claim3_id = claim3.id
        assert vc.run_verification(claim3_id) is False
        with get_session() as session:
            assert session.get(ExtractedClaim, claim3_id).verification is None
        print("Failure path OK")

        assert vc.run_verification(999999) is False
        print("Nonexistent claim handled OK")
    finally:
        vc.verify_claim_text = original_verify
        with get_session() as session:
            session.delete(session.get(VerificationDocument, doc_id))
            session.delete(session.get(Book, real_book_id))
finally:
    clients._qdrant_client = original_qdrant_client
    clients._openai_client = original_openai_client
    with get_session() as session:
        for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
            row = session.query(cls).filter_by(source_key=key).one_or_none()
            if row is not None:
                session.delete(row)

print("\nAll verify_claim assertions passed.")