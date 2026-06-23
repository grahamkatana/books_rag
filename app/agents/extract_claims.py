"""
Claim extraction: the second stage of the verification pipeline (after
app/ingestion/convert_docx.py's docx-to-markdown conversion). Splits the
markdown into sections small enough for one LLM call each, then runs a
pydantic-ai agent against each section to pull out genuinely checkable,
specific factual claims -- not every sentence. Filtering out opinion,
transitions, and non-factual prose is this agent's actual job; whatever
it returns is exactly what gets verified later, nothing more.

A separate agent from verification (app/agents/verify_claim.py, once
that exists) on purpose, per the project's own framing: extraction and
verification are genuinely different tasks with different failure
modes, and pydantic-ai's whole value here is forcing each one's output
into a validated schema rather than parsing free text by hand.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.config import DEFAULT_CHAT_MODEL
from app.db.session import get_session
from app.models.verification import VerificationDocument, ExtractedClaim
from app.logging_config import get_logger

logger = get_logger(__name__)

MAX_SECTION_CHARS = 6000  # comfortably within context for one extraction call, even for a verbose section


class ExtractedClaimItem(BaseModel):
    text: str = Field(
        description="The exact claim, quoted verbatim (character-for-character) from the "
                     "source text -- not paraphrased, not summarized. Verbatim quoting is "
                     "required so this claim's text can be matched back to its exact location "
                     "in the document later."
    )


class ClaimExtractionResult(BaseModel):
    claims: list[ExtractedClaimItem]


EXTRACTION_SYSTEM_PROMPT = (
    "You extract checkable factual claims from academic/professional writing. "
    "A checkable claim is a specific, falsifiable assertion of fact -- a statistic, "
    "a stated finding, a causal or comparative assertion, a claim about what a source "
    "says or shows. "
    "Do NOT extract: opinions, value judgments, transitional or structural sentences "
    "(e.g. 'This chapter discusses...'), rhetorical questions, or claims so general "
    "they aren't really checkable (e.g. 'software is important'). "
    "Quote each claim VERBATIM, character-for-character, exactly as it appears in the "
    "source text -- never paraphrase or summarize it, even slightly. If a sentence "
    "contains a checkable claim embedded in non-checkable framing, quote only the "
    "checkable portion verbatim. "
    "If a section contains no genuinely checkable claims, return an empty list -- "
    "do not invent claims to have something to return."
)


def build_extraction_agent(model: str = DEFAULT_CHAT_MODEL) -> Agent:
    # "openai-chat:" rather than "openai:" deliberately -- pydantic-ai's
    # own deprecation warning states "openai:" will resolve to the
    # Responses API by default starting in v2.0. Pinning explicitly now
    # means a future pydantic-ai upgrade can't silently change which
    # API this actually calls.
    return Agent(
        f"openai-chat:{model}",
        output_type=ClaimExtractionResult,
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
    )


def split_into_sections(markdown: str, max_chars: int = MAX_SECTION_CHARS) -> list[str]:
    """Greedily groups paragraphs (split on blank lines) into sections
    up to max_chars each. Simple on purpose: this only needs to keep
    each LLM call's input within a reasonable size, not produce
    perfectly-balanced or heading-aware chunks the way the book/paper
    pipelines' chunkers do -- there's no embedding or page-locator
    concern here, just "small enough to extract from in one call."""
    paragraphs = [p for p in markdown.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    sections = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len > max_chars:
            sections.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len

    if current:
        sections.append("\n\n".join(current))

    return sections


def extract_claims_from_section(section_text: str, agent: Agent | None = None) -> list[str]:
    """Runs the extraction agent against one section, returning the
    claim texts only -- the caller doesn't need ExtractedClaimItem's
    wrapper, just the strings, to build ExtractedClaim rows from."""
    agent = agent or build_extraction_agent()
    result = agent.run_sync(section_text)
    return [item.text for item in result.output.claims]


def extract_claims(markdown: str, agent: Agent | None = None) -> list[str]:
    """Splits the full document and extracts claims section by section,
    returning them in document order. One agent instance is built once
    and reused across all sections (a fresh Agent per section would
    work identically but rebuilds the same system prompt/config
    pointlessly for every call)."""
    agent = agent or build_extraction_agent()
    all_claims: list[str] = []
    for section in split_into_sections(markdown):
        all_claims.extend(extract_claims_from_section(section, agent=agent))
    return all_claims


def run_claim_extraction(document_id: int) -> int:
    """Reads the document's markdown, extracts its claims, writes them
    as ExtractedClaim rows, and advances status to "verifying" -- or
    "failed" with error_message set, never raising past this function,
    the same pattern convert_docx.py's ingest_verification_document()
    already follows. Returns how many claims were extracted."""
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is None:
            logger.error("run_claim_extraction: no document with id %s", document_id)
            return 0
        markdown = doc.markdown

    if not markdown:
        _mark_failed(document_id, "No markdown available -- conversion may not have completed.")
        return 0

    try:
        claim_texts = extract_claims(markdown)
    except Exception as e:
        logger.error("Claim extraction failed for document %s: %s", document_id, e)
        _mark_failed(document_id, f"Claim extraction failed: {e}")
        return 0

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        for i, text in enumerate(claim_texts):
            session.add(ExtractedClaim(document_id=document_id, text=text, order_index=i))
        doc.status = "verifying"

    logger.info("Document %s: extracted %d claim(s)", document_id, len(claim_texts))
    return len(claim_texts)


def _mark_failed(document_id: int, error_message: str) -> None:
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error_message = error_message