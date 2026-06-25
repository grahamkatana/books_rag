"""
Cross-checks a claim's verification using a different model provider
(Claude/Anthropic) than the primary verification agent (OpenAI) -- an
independent second opinion, not another retrieval pass.

Deliberately reviews the SAME evidence the primary verification cited,
rather than re-researching the claim from scratch: the question this
asks isn't "what does the evidence say" again, it's "does the verdict
actually follow from this evidence" -- a check on the reasoning step
specifically, which is exactly where real failures were found and
fixed elsewhere in this pipeline (a claim marked SUPPORTED on the
strength of an unrelated textbook's example exercise; claims marked
CONTRADICTED that were never externally checkable to begin with). A
genuinely different model provider matters here, not just a second
instance of the same one -- two same-provider models share correlated
blind spots in a way two different model families are less likely to.
"""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.config import CROSS_CHECK_MODEL
from app.db.session import get_session
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification, ClaimCrossCheck
from app.logging_config import get_logger

logger = get_logger(__name__)

Verdict = Literal["supported", "partially_supported", "contradicted", "unverifiable"]
Confidence = Literal["high", "medium", "low"]

# error is deliberately excluded -- if verification itself never
# completed, there's no reasoning to review, just a failure to retry.
REVIEWABLE_VERDICTS = ["supported", "partially_supported", "contradicted", "unverifiable"]


class CrossCheckResult(BaseModel):
    agrees: bool = Field(description="Whether you agree with the original verdict, at the confidence level claimed")
    verdict: Verdict = Field(
        description="Your own independent verdict -- what you think the correct verdict actually is, "
                     "regardless of whether it matches the original"
    )
    confidence: Confidence
    explanation: str = Field(
        description="A few sentences explaining your judgment, specifically addressing whether the "
                     "cited evidence actually supports the original verdict"
    )
    is_checkable_claim: bool = Field(
        default=True,
        description="False if this isn't actually an externally-checkable claim at all -- for example "
                     "if it describes the document's own aims, scope, or methodology rather than a fact "
                     "about the world."
    )


CROSS_CHECK_SYSTEM_PROMPT = (
    "You are an independent reviewer checking another AI system's verification of a claim. "
    "You will be given the claim, the verdict it reached, its explanation, and the specific "
    "evidence it cited. Your job is NOT to re-research the claim or search for new evidence -- "
    "it is to judge whether the cited evidence actually supports the verdict reached, using "
    "only what's provided. "
    "Agree if the evidence genuinely supports the stated verdict, to the degree of confidence "
    "claimed. Disagree if the evidence doesn't actually say what the explanation claims it "
    "says, if the evidence is irrelevant or about a different subject entirely, or if the "
    "verdict is more or less confident than the evidence actually justifies. "
    "Separately from whether you agree, always give your own independent verdict -- if you "
    "disagree, say what you think the correct verdict actually is, not just that the original "
    "one was wrong. "
    "Also judge, regardless of the verdict: is this actually an externally-checkable claim at "
    "all? A statement describing what THIS document itself aims to do, its own research "
    "design, or its own intended contributions is not checkable against any external evidence, "
    "no matter what evidence was cited for it -- the only thing such a statement could be "
    "checked against is the document making it. Set is_checkable_claim to false in that case, "
    "regardless of whatever verdict was originally reached."
)


def build_cross_check_agent(model: str = CROSS_CHECK_MODEL) -> Agent:
    return Agent(
        f"anthropic:{model}",
        output_type=CrossCheckResult,
        system_prompt=CROSS_CHECK_SYSTEM_PROMPT,
    )


def format_verification_for_review(claim_text: str, verification: ClaimVerification) -> str:
    """Builds the review prompt from live ORM data -- called while a
    session is still open, so the result is a plain string the actual
    agent call (outside any session) can use without needing the
    database at all. Reuses claim_evidence_to_dict's existing
    book/paper/web title resolution rather than re-deriving it here."""
    from app.api.v1.serializers import claim_evidence_to_dict

    lines = [
        f"Claim: {claim_text}",
        "",
        f"Original verdict: {verification.verdict} ({verification.confidence} confidence)",
        f"Original explanation: {verification.explanation}",
        "",
        "Evidence cited:",
    ]
    if not verification.evidence:
        lines.append("(none -- the original verification cited no evidence at all)")
    else:
        for i, evidence in enumerate(verification.evidence, start=1):
            e = claim_evidence_to_dict(evidence)
            source = e["title"] or "(untitled source)"
            if e.get("locator"):
                source += f", {e['locator']}"
            lines.append(f"[{i}] {source}\n{e['excerpt']}")
    return "\n".join(lines)


def cross_check_claim_text(review_prompt: str, agent: Agent | None = None) -> CrossCheckResult:
    agent = agent or build_cross_check_agent()
    result = agent.run_sync(review_prompt)
    return result.output


def run_cross_check(claim_id: int) -> bool:
    """Reads the claim and its existing verification, runs the
    cross-check, and persists a ClaimCrossCheck row -- replacing any
    existing one for this verification, so re-running this is always
    safe rather than accumulating stale rows. Returns True on success,
    False on failure (logged, never raised), the same pattern
    run_verification() already follows, so a caller cross-checking
    many claims in sequence can continue past one failure rather than
    abort the whole document."""
    with get_session() as session:
        claim = session.get(ExtractedClaim, claim_id)
        if claim is None:
            logger.error("run_cross_check: no claim with id %s", claim_id)
            return False
        if claim.verification is None:
            logger.error("run_cross_check: claim %s has no verification yet -- nothing to cross-check", claim_id)
            return False
        review_prompt = format_verification_for_review(claim.text, claim.verification)
        verification_id = claim.verification.id

    try:
        result = cross_check_claim_text(review_prompt)
    except Exception as e:
        logger.error("Cross-check failed for claim %s: %s", claim_id, e)
        return False

    with get_session() as session:
        verification = session.get(ClaimVerification, verification_id)
        if verification.cross_check is not None:
            session.delete(verification.cross_check)
            session.flush()
        session.add(ClaimCrossCheck(
            verification_id=verification_id,
            agrees=result.agrees,
            verdict=result.verdict,
            confidence=result.confidence,
            explanation=result.explanation,
            is_checkable_claim=result.is_checkable_claim,
            model=CROSS_CHECK_MODEL,
        ))

    logger.info("Claim %s cross-checked: agrees=%s, cross-check verdict=%s", claim_id, result.agrees, result.verdict)
    return True


def cross_check_document(document_id: int, verdicts_to_check: list[str] | None = None) -> dict:
    """Cross-checks every claim in the document whose verdict is in
    verdicts_to_check (default: every real verdict category --
    "error" claims are excluded, since there's no reasoning to review
    when verification itself never completed). Returns a summary: how
    many were actually checked, how many agreed/disagreed, and how
    many the cross-check itself flagged as not genuinely checkable at
    all -- a second, independent line of defense against the same
    extraction-stage failure mode EXTRACTION_SYSTEM_PROMPT was already
    tightened against, in case a claim slips through anyway."""
    target_verdicts = verdicts_to_check or REVIEWABLE_VERDICTS

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is None:
            logger.error("cross_check_document: no document with id %s", document_id)
            return {"document_id": document_id, "error": "document not found"}
        claim_ids = [
            c.id for c in doc.claims
            if c.verification is not None and c.verification.verdict in target_verdicts
        ]

    checked = agreed = disagreed = flagged_not_checkable = 0
    for claim_id in claim_ids:
        if not run_cross_check(claim_id):
            continue
        checked += 1
        with get_session() as session:
            claim = session.get(ExtractedClaim, claim_id)
            cc = claim.verification.cross_check
            if cc.agrees:
                agreed += 1
            else:
                disagreed += 1
            if not cc.is_checkable_claim:
                flagged_not_checkable += 1

    result = {
        "document_id": document_id, "checked": checked, "agreed": agreed,
        "disagreed": disagreed, "flagged_not_checkable": flagged_not_checkable,
    }
    logger.info("cross_check_document finished for document %s: %s", document_id, result)
    return result