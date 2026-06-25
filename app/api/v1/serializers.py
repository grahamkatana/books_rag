"""
Converts ORM objects into plain dicts while the DB session that loaded
them is still open. flask-smorest's @blp.response() decorator serializes
whatever a view function returns *after* the view function has already
returned -- by which point a `with get_session()` block has already
closed and any lazy attribute access would raise DetachedInstanceError.
Building plain dicts up front avoids that entirely.
"""

from app.models.book import Book
from app.models.chat import Chat, Message, Citation


def citation_to_dict(c: Citation) -> dict:
    return {"apa_text": c.apa_text, "locator": c.locator, "book_id": c.book_id, "paper_id": c.paper_id}


def message_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at,
        "citations": [citation_to_dict(c) for c in m.citations],
    }


def chat_to_summary_dict(c: Chat) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "created_at": c.created_at,
        "message_count": len(c.messages),
    }


def chat_to_detail_dict(c: Chat) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "created_at": c.created_at,
        "messages": [message_to_dict(m) for m in c.messages],
    }


def book_to_dict(b: Book) -> dict:
    return {
        "id": b.id,
        "source_key": b.source_key,
        "title": b.title,
        "authors": b.authors,
        "is_editor": b.is_editor,
        "year": b.year,
        "publisher": b.publisher,
        "edition": b.edition,
        "page_mode": b.page_mode,
        "work_key": b.work_key,
        "is_preferred_edition": b.is_preferred_edition,
        "bibliography_verified": b.bibliography_verified,
    }


def paper_to_dict(p) -> dict:
    return {
        "id": p.id,
        "source_key": p.source_key,
        "title": p.title,
        "authors": p.authors,
        "year": p.year,
        "venue": p.venue,
        "doi": p.doi,
        "abstract": p.abstract,
        "bibliography_verified": p.bibliography_verified,
    }


def claim_evidence_to_dict(evidence) -> dict:
    # evidence.book/.paper are real relationships (see app/models/
    # verification.py), so the resolved title comes for free here --
    # no second lookup needed, and no N+1 if the caller eager-loaded
    # the chain, which verification_document_to_detail_dict below does
    # simply by walking the ORM relationships it already has in hand.
    if evidence.book is not None:
        title = evidence.book.title
    elif evidence.paper is not None:
        title = evidence.paper.title
    else:
        title = evidence.web_title

    return {
        "book_id": evidence.book_id,
        "paper_id": evidence.paper_id,
        "web_url": evidence.web_url,
        "title": title,
        "excerpt": evidence.excerpt,
        "locator": evidence.locator,
    }


def claim_cross_check_to_dict(cross_check) -> dict:
    return {
        "agrees": cross_check.agrees,
        "verdict": cross_check.verdict,
        "confidence": cross_check.confidence,
        "explanation": cross_check.explanation,
        "is_checkable_claim": cross_check.is_checkable_claim,
        "model": cross_check.model,
    }


def claim_verification_to_dict(verification) -> dict:
    return {
        "verdict": verification.verdict,
        "confidence": verification.confidence,
        "explanation": verification.explanation,
        "evidence": [claim_evidence_to_dict(e) for e in verification.evidence],
        "cross_check": claim_cross_check_to_dict(verification.cross_check) if verification.cross_check else None,
    }


def extracted_claim_to_dict(claim) -> dict:
    return {
        "id": claim.id,
        "text": claim.text,
        "order_index": claim.order_index,
        "verification": claim_verification_to_dict(claim.verification) if claim.verification else None,
    }


def verification_document_to_summary_dict(doc) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "claim_count": len(doc.claims),
    }


def verification_document_to_detail_dict(doc) -> dict:
    return {
        **verification_document_to_summary_dict(doc),
        "markdown": doc.markdown,
        "claims": [extracted_claim_to_dict(c) for c in doc.claims],
    }