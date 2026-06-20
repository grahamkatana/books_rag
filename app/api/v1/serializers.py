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
    return {"apa_text": c.apa_text, "locator": c.locator, "book_id": c.book_id}


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
