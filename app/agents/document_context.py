"""
Document-level context, gathered once before extraction/verification
begin, using a cheap/fast model (Gemini, deliberately a much cheaper
model than either the extraction or verification agent -- this is a
classification/orientation task, not one that needs frontier
reasoning). Reads the document and produces a short structured summary
of what kind of document this is, what it's about, and crucially, what
the document itself claims to be doing (its own stated aims, scope, or
methodology) -- so later stages have that context available from the
start, rather than discovering it piecemeal, section by section, with
no memory of what came before.

This directly complements EXTRACTION_SYSTEM_PROMPT's own fix for the
same underlying failure mode (a document's self-referential statements
about its own aims/methodology getting misextracted as external
claims): with this context in hand up front, a section deep in a
literature review that happens to also restate "this study aims to..."
has a much better chance of being recognized correctly, since the
extraction agent already knows, from the very first section, that this
is exactly that kind of document -- not just for the one section where
that fact was first introduced.

Best-effort and optional throughout: a failure here never blocks the
pipeline. Extraction and verification both work fine without this
context (they always did, before this stage existed) -- a failure just
means they proceed with slightly less situational awareness, not that
the whole document fails.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.config import CONTEXT_MODEL, MAX_CONTEXT_INPUT_CHARS
from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.logging_config import get_logger

logger = get_logger(__name__)


class DocumentContext(BaseModel):
    document_type: str = Field(
        description="What kind of document this is, e.g. 'Master's thesis research proposal', "
                     "'published academic paper', 'technical report', 'policy white paper'"
    )
    subject_summary: str = Field(description="A few sentences on what the document is actually about or studying")
    self_description: str | None = Field(
        default=None,
        description="If the document describes ITS OWN aims, scope, methodology, or intended contributions "
                     "anywhere (common in proposals and theses), summarize what it says about itself here -- "
                     "this helps later stages recognize self-referential statements wherever they appear in the "
                     "document, not just where they're first introduced. Leave null if the document doesn't "
                     "describe itself this way at all (e.g. a finished paper reporting completed results)."
    )
    notable_structural_elements: list[str] = Field(
        default_factory=list,
        description="Structural elements worth flagging for claim extraction, e.g. 'Appendix B contains a "
                     "project timeline/Gantt chart with bare date labels, not claims' or 'contains a glossary "
                     "of terms' or 'has a long reference list formatted as numbered citations'. Empty list if "
                     "nothing notable."
    )


CONTEXT_SYSTEM_PROMPT = (
    "You are given the text of a document (or a representative portion of a longer one). "
    "Produce a short, structured orientation to help a later, more careful review process: "
    "what kind of document this is, what it's actually about, and -- this matters most -- whether "
    "the document describes its OWN aims, scope, methodology, or intended contributions anywhere "
    "(very common in research proposals and theses, where the author describes what they themselves "
    "plan to study or how they plan to study it). If it does, summarize what it says about itself "
    "specifically, since that's the part most likely to be mistaken for an external, checkable fact "
    "later on if it isn't flagged now. Also note any structural elements (timelines, glossaries, "
    "tables) that a section-by-section claim-extraction pass might otherwise misread out of context."
)


def build_context_agent(model: str = CONTEXT_MODEL) -> Agent:
    return Agent(
        f"google:{model}",
        output_type=DocumentContext,
        system_prompt=CONTEXT_SYSTEM_PROMPT,
    )


def get_document_context(markdown: str, agent: Agent | None = None) -> DocumentContext:
    agent = agent or build_context_agent()
    truncated = markdown[:MAX_CONTEXT_INPUT_CHARS]
    result = agent.run_sync(truncated)
    return result.output


def format_context_for_prompts(context: DocumentContext) -> str:
    """Flattens the structured context into a short plain-text block
    later prompts can simply prepend -- the structure matters for
    getting Gemini to actually produce a self_description rather than
    skip it, but downstream consumers (the extraction and verification
    system prompts) just need a few sentences of orientation, not a
    second schema to parse."""
    lines = [f"This document is a {context.document_type}. {context.subject_summary}"]
    if context.self_description:
        lines.append(
            f"The document describes its own aims/methodology as follows -- statements like these are "
            f"NOT externally checkable claims, they describe what the author plans or intends for this "
            f"work itself: {context.self_description}"
        )
    if context.notable_structural_elements:
        lines.append("Notable structure: " + "; ".join(context.notable_structural_elements))
    return " ".join(lines)


def run_document_context(document_id: int) -> bool:
    """Reads the document's markdown, gathers its context via Gemini,
    and stores it on the row. Returns True on success, False on
    failure (logged as a warning, never raised, never marks the
    document failed) -- see the module docstring for why this stage
    is allowed to fail without taking the rest of the pipeline down
    with it."""
    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        if doc is None:
            logger.error("run_document_context: no document with id %s", document_id)
            return False
        if not doc.markdown:
            logger.warning("run_document_context: document %s has no markdown yet, skipping", document_id)
            return False
        markdown = doc.markdown

    try:
        context = get_document_context(markdown)
    except Exception as e:
        logger.warning("Document context gathering failed for document %s, proceeding without it: %s", document_id, e)
        return False

    with get_session() as session:
        doc = session.get(VerificationDocument, document_id)
        doc.document_context = format_context_for_prompts(context)

    logger.info("Document %s: context gathered (%s)", document_id, context.document_type)
    return True