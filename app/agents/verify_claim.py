"""
Claim verification: the third stage of the verification pipeline, after
extraction (app/agents/extract_claims.py). One agent, not several --
web search and academic search are TOOLS this agent can choose between,
not separate agents, because deciding whether the corpus already
answers a claim (and if not, which kind of external search actually
fits it) is part of the verification judgment itself, not a distinct
task with its own failure mode the way extraction and verification are
from each other.

Corpus evidence is gathered BEFORE the agent runs, via the exact same
dual-corpus retrieval query_engine.py already uses (embed_query +
search_chunks(corpus="both")) -- no new retrieval logic, this is the
same infrastructure the chat itself uses, pointed at a claim instead of
a question. Two fallback tools exist for when the corpus doesn't
actually address a claim: search_web (the same search_brave()
lookup_bibliography.py already calls) for general factual/statistical
claims, and search_academic_papers (Crossref's works database, the
same registry app/ingestion/lookup_paper_doi.py already resolves real
papers against) for claims that look like they're citing a specific
study or author -- a thesis literature review is full of exactly that
kind of claim, and a personal book/paper library will essentially
never contain every paper someone else's bibliography cites. General
web search is a weak tool for finding a specific academic paper; this
gives the agent a second, better-suited tool for that specific case
rather than forcing every external lookup through one generic search.
"""

from dataclasses import dataclass, field
from typing import Literal

import requests
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from app.config import DEFAULT_CHAT_MODEL, DEFAULT_TOP_K, CROSSREF_MAILTO
from app.api.clients import get_openai_client, get_qdrant_client
from app.db.session import get_session
from app.models.book import Book
from app.models.paper import Paper
from app.models.verification import ExtractedClaim, ClaimVerification, ClaimEvidence
from app.retrieval.query_engine import embed_query, search_chunks
from app.retrieval.citations import build_locator
from app.ingestion.lookup_bibliography import search_brave, search_serpapi
from app.ingestion.lookup_paper_doi import format_authors, extract_year
from app.logging_config import get_logger

logger = get_logger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"

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
    "You have two fallback tools for when the provided corpus evidence does not address the "
    "claim at all -- do not use either one if the corpus evidence is already sufficient to "
    "reach a verdict, even a low-confidence one. "
    "Use search_academic_papers when the claim cites, or appears to paraphrase, a specific "
    "study, author, or finding (e.g. 'Smith (2023) found that...', or a statistic that reads "
    "like it came from a particular study) -- this searches an actual academic registry "
    "(Crossref), which is far more likely to contain a specific paper than general web search "
    "is, and an empty result from it is itself informative: it means the cited source isn't in "
    "that registry either, not just that this library doesn't have it. "
    "Use search_web for general factual, statistical, or current-events claims that aren't "
    "tied to a specific academic source. "
    "You may sometimes be given document-level context before the claim, clearly marked as "
    "such. If it says the document describes its own aims, scope, or methodology, and the claim "
    "you're checking matches that self-description, mark it 'unverifiable' regardless of the "
    "evidence -- it is not contradicted, since it was never a claim about the external world to "
    "begin with, and no evidence could appropriately settle it either way. "
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


def search_crossref(query: str, count: int = 5) -> list[dict]:
    """A general, relevance-ranked search across Crossref's works
    database -- deliberately different from
    lookup_paper_doi.py's crossref_search_by_title(), which is built to
    identify ONE specific paper precisely by an exact title match. This
    one's job is finding several candidate papers that might support
    or contradict a claim, the same role search_brave() plays for
    general web evidence, just scoped to an actual academic registry
    instead of the open web. Returns whatever Crossref has, even if
    nothing's a strong match -- relevance judgment belongs to the
    calling agent, the same way it already judges corpus evidence."""
    try:
        params = {"query": query, "rows": count}
        if CROSSREF_MAILTO:
            params["mailto"] = CROSSREF_MAILTO
        response = requests.get(CROSSREF_WORKS_URL, params=params, timeout=15)
        response.raise_for_status()
        items = (response.json().get("message") or {}).get("items", [])
    except requests.RequestException as e:
        logger.warning("Crossref search failed for query %r: %s", query, e)
        return []

    results = []
    for item in items:
        title = (item.get("title") or [""])[0]
        if not title:
            continue
        results.append({
            "title": title,
            "authors": format_authors(item.get("author")),
            "year": extract_year(item),
            "doi": item.get("DOI"),
        })
    return results


def search_web_impl(ctx: RunContext[VerificationDeps], query: str) -> str:
    """Searches the general web for evidence about the claim. Best for
    factual, statistical, or general claims -- NOT for claims that cite
    a specific academic study or author, where search_academic_papers
    is the better-suited tool. A standalone function (registered onto
    the agent in build_verification_agent() below) rather than an
    inline @agent.tool closure, specifically so its actual behavior --
    appending to ctx.deps.all_evidence with correctly-continued
    indices, handling a failed or empty search -- is directly testable
    without needing to drive it through the agent's tool-calling
    machinery at all."""
    
    results = None
    
    # Primary attempt: Brave Search
    try:
        results = search_brave(query, count=5)
    except Exception as e:
        logger.warning("search_brave failed for query %r: %s. Falling back to SerpApi.", query, e)
        
        # Fallback attempt: SerpApi
        try:
            results = search_serpapi(query, count=5) 
        except Exception as serp_e:
            logger.warning("search_serpapi fallback failed for query %r: %s", query, serp_e)
            return "Web search failed -- reach a verdict using only the corpus evidence already provided."

    if not results:
        return "No web results found for that query."

    start_index = len(ctx.deps.all_evidence) + 1
    lines = []
    
    for i, r in enumerate(results):
        # Handle key discrepancies between Brave (description, url) and SerpApi (snippet, link)
        title = r.get("title", "")
        excerpt = r.get("description") or r.get("snippet", "")
        url = r.get("url") or r.get("link", "")
        
        ctx.deps.all_evidence.append({
            "source": "web",
            "book_id": None,
            "paper_id": None,
            "title": title,
            "excerpt": excerpt,
            "locator": None,
            "web_url": url,
            "web_title": title,
        })
        lines.append(f"[{start_index + i}] {title}\n{excerpt}\n{url}")
        
    return "\n\n".join(lines)

def search_academic_impl(ctx: RunContext[VerificationDeps], query: str) -> str:
    """Searches Crossref's academic works database for papers relevant
    to the claim. Use this INSTEAD of search_web when the claim cites,
    or appears to paraphrase, a specific study, author, or finding --
    general web search rarely surfaces the actual paper for something
    like that, while Crossref's registry is built specifically to
    contain it (if it's findable at all -- the result may legitimately
    be empty, which itself is useful information: it means the claim's
    cited source isn't in Crossref's index either, not just that this
    library doesn't have it). Same evidence-list mechanics as
    search_web_impl: indices continue from whatever's already in
    ctx.deps.all_evidence, corpus or web alike, so the agent's final
    citation indices always resolve against one single, consistently-
    numbered list regardless of which tool (or none) supplied a given
    piece of evidence."""
    results = search_crossref(query, count=5)

    if not results:
        return "No matching papers found in Crossref for that query."

    start_index = len(ctx.deps.all_evidence) + 1
    lines = []
    for i, r in enumerate(results):
        excerpt_parts = [r["title"]]
        if r.get("authors"):
            excerpt_parts.append(r["authors"])
        if r.get("year"):
            excerpt_parts.append(str(r["year"]))
        excerpt = ", ".join(excerpt_parts)

        doi_url = f"https://doi.org/{r['doi']}" if r.get("doi") else None
        ctx.deps.all_evidence.append({
            "source": "web",
            "book_id": None,
            "paper_id": None,
            "title": r["title"],
            "excerpt": excerpt,
            "locator": None,
            "web_url": doi_url,
            "web_title": r["title"],
        })
        lines.append(f"[{start_index + i}] {excerpt}" + (f"\n{doi_url}" if doi_url else ""))
    return "\n\n".join(lines)


def build_verification_agent(model: str = DEFAULT_CHAT_MODEL) -> Agent:
    agent = Agent(
        f"openai-chat:{model}",
        output_type=VerificationVerdict,
        system_prompt=VERIFICATION_SYSTEM_PROMPT,
        deps_type=VerificationDeps,
    )
    agent.tool(search_web_impl)
    agent.tool(search_academic_impl)
    return agent


def format_evidence_list(evidence: list[dict]) -> str:
    if not evidence:
        return "(no corpus evidence found for this claim)"
    lines = []
    for i, e in enumerate(evidence, start=1):
        lines.append(f"[{i}] {e['title']}" + (f" ({e['locator']})" if e.get("locator") else "") + f"\n{e['excerpt']}")
    return "\n\n".join(lines)


def verify_claim_text(claim_text: str, agent: Agent | None = None, top_k: int = DEFAULT_TOP_K, document_context: str | None = None) -> tuple[VerificationVerdict, list[dict]]:
    """Gathers corpus evidence, runs the verification agent (which may
    call search_web or search_academic_papers itself), and returns the
    verdict alongside the final, complete evidence list (corpus + any
    web/academic results the agent actually triggered) -- ready for the
    caller to persist.

    document_context, when available (see app/agents/document_context.py),
    is prepended ahead of the claim and evidence, clearly delineated --
    most useful for the same case it helps extraction with: recognizing
    that a claim is the document's own self-referential statement about
    its own aims/methodology, which no evidence could ever appropriately
    settle, rather than treating it as a normal external claim that
    happens to have thin evidence."""
    agent = agent or build_verification_agent()
    deps = VerificationDeps(all_evidence=gather_corpus_evidence(claim_text, top_k=top_k))

    prompt = f"Claim to verify:\n{claim_text}\n\nEvidence:\n{format_evidence_list(deps.all_evidence)}"
    if document_context:
        prompt = f"Document context (for your understanding only):\n{document_context}\n\n---\n\n{prompt}"
    result = agent.run_sync(prompt, deps=deps)

    return result.output, deps.all_evidence


def run_verification(claim_id: int) -> bool:
    """Reads the claim, verifies it, and persists a ClaimVerification
    row plus one ClaimEvidence row per cited source. Returns True on
    success, False on failure -- failures are logged, not raised, so a
    caller verifying many claims in sequence (verify_document_claims)
    can continue past one claim's failure rather than abort the whole
    document.

    A failure still gets a real ClaimVerification row, with
    verdict="error" and the actual exception message as the
    explanation -- this is deliberate, not a relaxed version of the
    happy path. Without it, a claim that errored out (a transient rate
    limit, a quota exhausted mid-document) is stored identically to one
    that simply hasn't been verified yet: both would have
    verification=None, and a caller has no way to tell "still queued"
    apart from "this one broke and isn't coming back." verdict="error"
    is never something the LLM itself produces (it's outside
    VerificationVerdict's Literal type entirely) -- it only ever comes
    from this except block, so its presence on a row unambiguously
    means the agent call itself failed, not that it reached a low-
    confidence conclusion."""
    with get_session() as session:
        claim = session.get(ExtractedClaim, claim_id)
        if claim is None:
            logger.error("run_verification: no claim with id %s", claim_id)
            return False
        claim_text = claim.text
        document_context = claim.document.document_context

    try:
        verdict, all_evidence = verify_claim_text(claim_text, document_context=document_context)
    except Exception as e:
        logger.error("Verification failed for claim %s: %s", claim_id, e)
        with get_session() as session:
            session.add(ClaimVerification(
                claim_id=claim_id,
                verdict="error",
                confidence="low",
                explanation=f"Verification failed: {e}",
            ))
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