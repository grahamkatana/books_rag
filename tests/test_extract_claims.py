import sys, warnings
sys.path.insert(0, ".")

import os
os.environ.setdefault("OPENAI_API_KEY", "dummy-test-key")  # agent construction needs a key present even
                                                              # though TestModel below ensures no real call happens

from pydantic_ai.models.test import TestModel

from app.db.session import get_session
from app.models.verification import VerificationDocument, ExtractedClaim
import app.agents.extract_claims as ec

# --- split_into_sections: pure logic ---
md = "Paragraph one.\n\n" + ("x" * 5000) + "\n\nParagraph three is short."
sections = ec.split_into_sections(md, max_chars=4000)
assert len(sections) >= 2, "an oversized paragraph should force a new section"
assert ec.split_into_sections("") == []
assert ec.split_into_sections("   \n\n  ") == []
assert ec.split_into_sections("One.\n\nTwo.\n\nThree.", max_chars=1000) == ["One.\n\nTwo.\n\nThree."]
print("split_into_sections assertions passed.")

# --- agent plumbing via pydantic-ai's own TestModel, no real API call ---
agent = ec.build_extraction_agent()

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    fake_result = ec.ClaimExtractionResult(claims=[
        ec.ExtractedClaimItem(text="AI adoption has doubled since 2023."),
        ec.ExtractedClaimItem(text="42% of code is now AI-generated."),
    ])
    with agent.override(model=TestModel(custom_output_args=fake_result.model_dump())):
        claims = ec.extract_claims_from_section("Some section about AI adoption.", agent=agent)
    model_prefix_warnings = [str(w.message) for w in caught if "will resolve to the OpenAI Responses API" in str(w.message)]
    assert not model_prefix_warnings, "the openai-chat: pin regressed -- pydantic-ai model prefix warning reappeared"

assert claims == ["AI adoption has doubled since 2023.", "42% of code is now AI-generated."]

empty_result = ec.ClaimExtractionResult(claims=[])
with agent.override(model=TestModel(custom_output_args=empty_result.model_dump())):
    assert ec.extract_claims_from_section("Nothing checkable here.", agent=agent) == []
print("Agent plumbing assertions passed (including the openai-chat: pin staying in place).")

# --- run_claim_extraction: full orchestration ---
print("\n--- success path ---")
with get_session() as session:
    doc = VerificationDocument(filename="test.docx", status="extracting_claims", markdown="Some markdown content.")
    session.add(doc)
    session.flush()
    doc_id = doc.id

original_extract_claims = ec.extract_claims
ec.extract_claims = lambda markdown, agent=None: ["Claim one.", "Claim two.", "Claim three."]
try:
    count = ec.run_claim_extraction(doc_id)
    assert count == 3
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        assert doc.status == "verifying"
        claims = session.query(ExtractedClaim).filter_by(document_id=doc_id).order_by(ExtractedClaim.order_index).all()
        assert [c.text for c in claims] == ["Claim one.", "Claim two.", "Claim three."]
        assert [c.order_index for c in claims] == [0, 1, 2]
        session.delete(doc)
    print("OK")

    print("\n--- no markdown: fails immediately, extraction never attempted ---")
    extraction_called = {"value": False}

    def track_extraction(markdown, agent=None):
        extraction_called["value"] = True
        return []

    ec.extract_claims = track_extraction
    with get_session() as session:
        doc = VerificationDocument(filename="no_markdown.docx", status="converting", markdown=None)
        session.add(doc)
        session.flush()
        doc_id2 = doc.id

    count2 = ec.run_claim_extraction(doc_id2)
    assert count2 == 0
    assert extraction_called["value"] is False
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id2)
        assert doc.status == "failed"
        session.delete(doc)
    print("OK")

    print("\n--- extraction raises: failed, no partial claims written ---")
    def raise_extraction_error(markdown, agent=None):
        raise RuntimeError("simulated agent failure")

    ec.extract_claims = raise_extraction_error
    with get_session() as session:
        doc = VerificationDocument(filename="extraction_fails.docx", status="extracting_claims", markdown="content")
        session.add(doc)
        session.flush()
        doc_id3 = doc.id

    count3 = ec.run_claim_extraction(doc_id3)
    assert count3 == 0
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id3)
        assert doc.status == "failed"
        assert "simulated agent failure" in doc.error_message
        assert session.query(ExtractedClaim).filter_by(document_id=doc_id3).count() == 0
        session.delete(doc)
    print("OK")

    print("\n--- nonexistent document_id: returns 0, does not crash ---")
    assert ec.run_claim_extraction(999999) == 0
    print("OK")
finally:
    ec.extract_claims = original_extract_claims

print("\nAll claim-extraction assertions passed.")