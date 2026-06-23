"""
Claim verification: the third stage of the verification pipeline, after
extraction (app/agents/extract_claims.py). One agent, not several --
the web search capability is a TOOL this agent can choose to call, not
a separate agent, because deciding whether the corpus already answers a
claim is part of the verification judgment itself, not a distinct task
with its own failure mode the way extraction and verification are from
each other.

Corpus evidence is gathered BEFORE the agent runs, via the exact same
dual-corpus retrieval query_engine.py already uses (embed_query +
search_chunks(corpus="both")) -- no new retrieval logic, this is the
same infrastructure the chat itself uses, pointed at a claim instead of
a question. The agent only reaches for Brave (the same search_brave()
lookup_bibliography.py already calls) when it judges the corpus
evidence doesn't actually address the claim -- using your own library
first, the web as a genuine fallback, not a default.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from app.config import DEFAULT_CHAT_MODEL, DEFAULT_TOP_K
from app.api.clients import get_openai_client, get_qdrant_client
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.verification import ExtractedClaim, ClaimVerification, ClaimEvidence
from app.retrieval.query_engine import embed_query, search_chunks
from app.retrieval.citations import build_locator
from app.ingestion.lookup_bibliography import search_brave
from app.logging_config import get_logger

logger = get_logger(__name__)

Verdict = Literal["supported", "partially_supported", "contradicted", "unverifiable"]
Confidence = Literal["high", "medium", "low"]


class EvidenceCitation(BaseModel):
    source_index: int = Field(description="The number of the evidence item from the numbered list provided, e.g. 1 for evidence [1]")
    relevance_note: str = Field(description="One short sentence on how this specific evidence supports, partially supports, or contradicts the claim")


class VerificationVerdict(BaseModel):
    verdict: Verdict
    confidence: Confidence
    explanation: str = Field(description="A few sentences explaining the verdict in plain language, referencing the evidence used")
    evidence_cited: list[EvidenceCitation] = Field(
        default_factory=list,
        description="Every evidence item actually used to reach this verdict, by index. Empty if verdict is 'unverifiable'.",
    )


@dataclass
class VerificationDeps:
    # Pre-populated with corpus evidence before the agent runs; the
    # search_web tool appends to this same list during the run, so the
    # agent's final evidence_cited indices always resolve against one
    # single, consistently-numbered list regardless of which source a
    # given piece of evidence came from.
    all_evidence: list[dict] = field(default_factory=list)


VERIFICATION_SYSTEM_PROMPT = (
    "You are verifying a single factual claim from an academic or professional document "
    "against a numbered list of evidence. "
    "Decide one verdict: "
    "'supported' if the evidence directly and clearly backs the claim as stated; "
    "'partially_supported' if the evidence backs part of the claim, a weaker or narrower "
    "version of it, or the claim overstates what the evidence actually shows; "
    "'contradicted' if the evidence directly conflicts with the claim; "
    "'unverifiable' if nothing provided addresses the claim either way. "
    "Assign confidence based on how directly the evidence speaks to the claim and how much "
    "of it agrees -- 'low' confidence is correct and expected when evidence is thin or mixed, "
    "do not inflate confidence to seem more certain than the evidence supports. "
    "You have a search_web tool. Use it ONLY if the provided corpus evidence does not "
    "address the claim at all -- do not use it if the corpus evidence is already sufficient "
    "to reach a verdict, even a low-confidence one. "
    "Cite every evidence item you actually relied on in evidence_cited, by its number in the "
    "list. Never cite an evidence item that doesn't actually support your stated verdict."
)


def gather_corpus_evidence(claim_text: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Embeds the claim and searches both book_library and paper_library
    -- the exact same retrieval path query_engine.py uses for a chat
    question, just pointed at a claim instead. Returns evidence dicts
    ready to both build the agent's prompt from and persist as
    ClaimEvidence rows afterward, without needing a second shape
    translation in between."""
    openai_client = get_openai_client()
    qdrant = get_qdrant_client()

    query_vector = embed_query(openai_client, claim_text)
    hits = search_chunks(qdrant, query_vector, top_k=top_k, corpus="both")

    evidence = []
    with get_session() as session:
        for h in hits:
            payload = h.payload
            source_key = payload.get("source")
            corpus = payload.get("_corpus", "books")

            book_id, paper_id, title = None, None, source_key
            if corpus == "papers":
                paper = session.query(Paper).filter_by(source_key=source_key).one_or_none()
                if paper is not None:
                    paper_id, title = paper.id, paper.title
            else:
                book = session.query(Book).filter_by(source_key=source_key).one_or_none()
                if book is not None:
                    book_id, title = book.id, book.title

            evidence.append({
                "source": "corpus",
                "book_id": book_id,
                "paper_id": paper_id,
                "title": title,
                "excerpt": payload.get("text", ""),
                "locator": build_locator(payload),
                "web_url": None,
                "web_title": None,
            })

    return evidence


def search_web_impl(ctx: RunContext[VerificationDeps], query: str) -> str:
    """Searches the web for evidence about the claim. Only use this if
    the corpus evidence already provided doesn't address the claim at
    all. A standalone function (registered onto the agent in
    build_verification_agent() below) rather than an inline @agent.tool
    closure, specifically so its actual behavior -- appending to
    ctx.deps.all_evidence with correctly-continued indices, handling a
    failed or empty search -- is directly testable without needing to
    drive it through the agent's tool-calling machinery at all."""
    try:
        results = search_brave(query, count=5)
    except Exception as e:
        logger.warning("search_web tool call failed for query %r: %s", query, e)
        return "Web search failed -- reach a verdict using only the corpus evidence already provided."

    if not results:
        return "No web results found for that query."

    start_index = len(ctx.deps.all_evidence) + 1
    lines = []
    for i, r in enumerate(results):
        ctx.deps.all_evidence.append({
            "source": "web",
            "book_id": None,
            "paper_id": None,
            "title": r.get("title", ""),
            "excerpt": r.get("description", ""),
            "locator": None,
            "web_url": r.get("url"),
            "web_title": r.get("title"),
        })
        lines.append(f"[{start_index + i}] {r.get('title', '')}\n{r.get('description', '')}\n{r.get('url', '')}")
    return "\n\n".join(lines)


def build_verification_agent(model: str = DEFAULT_CHAT_MODEL) -> Agent:
    agent = Agent(
        f"openai-chat:{model}",
        output_type=VerificationVerdict,
        system_prompt=VERIFICATION_SYSTEM_PROMPT,
        deps_type=VerificationDeps,
    )
    agent.tool(search_web_impl)
    return agent


def format_evidence_list(evidence: list[dict]) -> str:
    if not evidence:
        return "(no corpus evidence found for this claim)"
    lines = []
    for i, e in enumerate(evidence, start=1):
        lines.append(f"[{i}] {e['title']}" + (f" ({e['locator']})" if e.get("locator") else "") + f"\n{e['excerpt']}")
    return "\n\n".join(lines)


def verify_claim_text(claim_text: str, agent: Agent | None = None, top_k: int = DEFAULT_TOP_K) -> tuple[VerificationVerdict, list[dict]]:
    """Gathers corpus evidence, runs the verification agent (which may
    call search_web itself), and returns the verdict alongside the
    final, complete evidence list (corpus + any web results the agent
    actually triggered) -- ready for the caller to persist."""
    agent = agent or build_verification_agent()
    deps = VerificationDeps(all_evidence=gather_corpus_evidence(claim_text, top_k=top_k))

    prompt = f"Claim to verify:\n{claim_text}\n\nEvidence:\n{format_evidence_list(deps.all_evidence)}"
    result = agent.run_sync(prompt, deps=deps)

    return result.output, deps.all_evidence


def run_verification(claim_id: int) -> bool:
    """Reads the claim, verifies it, and persists a ClaimVerification
    row plus one ClaimEvidence row per cited source. Returns True on
    success, False on failure -- failures are logged, not raised, so a
    caller verifying many claims in sequence (the Celery task, once
    built) can continue past one claim's failure rather than abort the
    whole document."""
    with get_session() as session:
        claim = session.get(ExtractedClaim, claim_id)
        if claim is None:
            logger.error("run_verification: no claim with id %s", claim_id)
            return False
        claim_text = claim.text

    try:
        verdict, all_evidence = verify_claim_text(claim_text)
    except Exception as e:
        logger.error("Verification failed for claim %s: %s", claim_id, e)
        return False

    with get_session() as session:
        verification = ClaimVerification(
            claim_id=claim_id,
            verdict=verdict.verdict,
            confidence=verdict.confidence,
            explanation=verdict.explanation,
        )
        session.add(verification)
        session.flush()

        for order_index, citation in enumerate(verdict.evidence_cited):
            idx = citation.source_index - 1  # the agent sees 1-based indices in its prompt
            if not (0 <= idx < len(all_evidence)):
                logger.warning("Claim %s: agent cited evidence index %s, out of range for %d items -- skipping",
                                claim_id, citation.source_index, len(all_evidence))
                continue
            e = all_evidence[idx]
            session.add(ClaimEvidence(
                verification_id=verification.id,
                book_id=e["book_id"],
                paper_id=e["paper_id"],
                web_url=e["web_url"],
                web_title=e["web_title"],
                excerpt=e["excerpt"],
                locator=e["locator"],
                order_index=order_index,
            ))

    logger.info("Claim %s verified: %s (%s confidence)", claim_id, verdict.verdict, verdict.confidence)
    return True