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

# --- extract_claims itself: per-section isolation, not just run_claim_extraction's handling of it ---
print("\n--- extract_claims isolates a failing section instead of aborting the whole document ---")
# Each paragraph needs to be large enough, on its own, to force a new
# section under extract_claims' own default MAX_SECTION_CHARS -- using
# a tiny custom max_chars here would test split_into_sections' behavior
# at a size extract_claims() itself never actually calls it with.
big_markdown = "\n\n".join(("Section content. " * 400) + f" marker-{i}" for i in range(5))
sections_seen = ec.split_into_sections(big_markdown)  # default max_chars, matching what extract_claims() actually uses
assert len(sections_seen) >= 3, f"need several sections for this test to mean anything, got {len(sections_seen)}"

original_extract_from_section = ec.extract_claims_from_section
call_count = {"n": 0}


def flaky_extraction(section_text, agent=None, document_context=None):
    call_count["n"] += 1
    if call_count["n"] == 2:  # the second section call fails; the rest succeed
        raise RuntimeError("simulated transient failure on one section")
    return [f"claim from call {call_count['n']}"]


ec.extract_claims_from_section = flaky_extraction
try:
    claim_texts, failed_sections, total_sections = ec.extract_claims(big_markdown)
    assert failed_sections == 1, f"expected exactly 1 failed section, got {failed_sections}"
    assert total_sections == len(sections_seen)
    assert len(claim_texts) == total_sections - 1, "every section except the failing one should still contribute its claim"
    assert "claim from call 2" not in claim_texts
finally:
    ec.extract_claims_from_section = original_extract_from_section
print("OK")

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
ec.extract_claims = lambda markdown, agent=None, document_context=None: (["Claim one.", "Claim two.", "Claim three."], 0, 1)
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

    def track_extraction(markdown, agent=None, document_context=None):
        extraction_called["value"] = True
        return ([], 0, 0)

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

    print("\n--- extract_claims itself raises: failed, no partial claims written ---")
    def raise_extraction_error(markdown, agent=None, document_context=None):
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

    print("\n--- partial section failure: proceeds with what succeeded, leaves a visible note, NOT marked failed ---")
    ec.extract_claims = lambda markdown, agent=None, document_context=None: (["Claim from a good section."], 12, 30)
    with get_session() as session:
        doc4 = VerificationDocument(filename="partial_failure.docx", status="extracting_claims", markdown="content")
        session.add(doc4)
        session.flush()
        doc4_id = doc4.id

    count4 = ec.run_claim_extraction(doc4_id)
    assert count4 == 1, "the claim from the sections that DID succeed must still be saved"
    with get_session() as session:
        doc4 = session.get(VerificationDocument, doc4_id)
        assert doc4.status == "verifying", "partial failure must not abort the document the way total failure does"
        assert doc4.error_message is not None and "12/30" in doc4.error_message
        claims4 = session.query(ExtractedClaim).filter_by(document_id=doc4_id).all()
        assert len(claims4) == 1
        session.delete(doc4)
    print("OK")

    print("\n--- every single section fails: this DOES fail the document (a sustained problem, not a blip) ---")
    ec.extract_claims = lambda markdown, agent=None, document_context=None: ([], 30, 30)
    with get_session() as session:
        doc5 = VerificationDocument(filename="total_failure.docx", status="extracting_claims", markdown="content")
        session.add(doc5)
        session.flush()
        doc5_id = doc5.id

    count5 = ec.run_claim_extraction(doc5_id)
    assert count5 == 0
    with get_session() as session:
        doc5 = session.get(VerificationDocument, doc5_id)
        assert doc5.status == "failed"
        assert "30/30" in doc5.error_message
        session.delete(doc5)
    print("OK")

    print("\n--- nonexistent document_id: returns 0, does not crash ---")
    assert ec.run_claim_extraction(999999) == 0
    print("OK")
finally:
    ec.extract_claims = original_extract_claims

print("\nAll claim-extraction assertions passed.")