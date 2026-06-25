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
    "Do NOT extract bare labels, headings, table cell contents, or standalone date/time "
    "references with no subject or assertion attached (e.g. a timeline row reading just "
    "'August 2026', or a section heading) -- these are document structure, not claims, "
    "even when they read as a sentence fragment in isolation. "
    "Do NOT extract statements describing THIS document's own aims, scope, research "
    "design, methodology, or intended contributions (e.g. 'This study aims to...', "
    "'The contributions of this study include...', 'Semi-structured interviews will be "
    "conducted with...', 'The research instrument is...'). These describe what the "
    "author plans or intends for the current, not-yet-completed work -- they are not "
    "facts about the external world, and cannot be meaningfully checked against any "
    "external source, since the only thing such a statement could be checked against "
    "is the document making it. "
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


def extract_claims(markdown: str, agent: Agent | None = None) -> tuple[list[str], int, int]:
    """Splits the full document and extracts claims section by section,
    returning them in document order. One agent instance is built once
    and reused across all sections (a fresh Agent per section would
    work identically but rebuilds the same system prompt/config
    pointlessly for every call).

    Returns (claim_texts, failed_section_count, total_section_count).
    Each section's extraction is isolated: a transient failure on one
    section (a rate limit, a network blip) is logged and skipped, not
    allowed to abort the whole document's extraction. This matters
    concretely once a document is long enough to need many sections --
    a 20-30 page document easily needs 25-30 sequential extraction
    calls, and the odds of at least one of them hitting a transient
    error are far higher than for a short document needing only one or
    two. Without this, that one failure would previously fail the
    entire document, discarding every claim already successfully
    extracted from every other section."""
    agent = agent or build_extraction_agent()
    all_claims: list[str] = []
    sections = split_into_sections(markdown)
    failed_sections = 0
    for i, section in enumerate(sections):
        try:
            all_claims.extend(extract_claims_from_section(section, agent=agent))
        except Exception as e:
            failed_sections += 1
            logger.warning("Claim extraction failed for section %d/%d, skipping it: %s", i + 1, len(sections), e)
    return all_claims, failed_sections, len(sections)


def run_claim_extraction(document_id: int) -> int:
    """Reads the document's markdown, extracts its claims, writes them
    as ExtractedClaim rows, and advances status to "verifying" -- or
    "failed" with error_message set, never raising past this function,
    the same pattern convert_docx.py's ingest_verification_document()
    already follows. Returns how many claims were extracted.

    Only fails the whole document if EVERY section's extraction call
    failed (a sustained outage or bad credentials, not a one-off
    blip) -- a partial failure still proceeds with whatever claims
    were actually extracted, with a note left on error_message so the
    gap is visible rather than silently invisible, even though the
    document itself isn't marked failed."""
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
        claim_texts, failed_sections, total_sections = extract_claims(markdown)
    except Exception as e:
        logger.error("Claim extraction failed for document %s: %s", document_id, e)
        _mark_failed(document_id, f"Claim extraction failed: {e}")
        return 0

    if total_sections > 0 and failed_sections == total_sections:
        _mark_failed(
            document_id,
            f"Claim extraction failed on every section ({failed_sections}/{total_sections}) -- "
            "likely a sustained API problem (quota, outage, bad credentials), not a one-off blip.",
        )
        return 0

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        for i, text in enumerate(claim_texts):
            session.add(ExtractedClaim(document_id=document_id, text=text, order_index=i))
        if failed_sections:
            doc.error_message = (
                f"{failed_sections}/{total_sections} section(s) of this document could not be processed "
                "during claim extraction -- claims from those sections are missing entirely, not just unverified."
            )
        doc.status = "verifying"

    logger.info("Document %s: extracted %d claim(s) (%d/%d sections failed)",
                document_id, len(claim_texts), failed_sections, total_sections)
    return len(claim_texts)


def _mark_failed(document_id: int, error_message: str) -> None:
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error_message = error_message