"""
Core retrieval + generation engine: embeds a question, searches Qdrant,
builds a citation-ready context, asks the LLM, and persists the full
turn (question + answer + parsed citations) to the chat history DB.
"""

from sqlalchemy.orm import Session

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny

from app.config import EMBEDDING_MODEL, QDRANT_COLLECTION, DEFAULT_CHAT_MODEL, DEFAULT_TOP_K
from app.models.book import Book
from app.models.chat import Chat, Message, Citation
from app.retrieval.citations import render_citation, extract_citation_tags, RenderedCitation


def _normalize_sources(source_filter) -> list[str] | None:
    """Accepts None, a single source_key string, or a list of them --
    always returns a list (or None), so callers can pass whichever shape
    is convenient without every call site needing to know the difference."""
    if not source_filter:
        return None
    if isinstance(source_filter, str):
        return [source_filter]
    return list(source_filter)


def embed_query(openai_client, text: str, model: str = EMBEDDING_MODEL) -> list:
    response = openai_client.embeddings.create(model=model, input=[text])
    return response.data[0].embedding


def get_excluded_source_keys(session: Session) -> list[str]:
    """Source keys for editions explicitly marked non-preferred (i.e. an
    older edition where a newer one is also in the library). Used to keep
    retrieval from silently blending two editions of the same book into
    one answer."""
    rows = session.query(Book.source_key).filter(
        Book.work_key.isnot(None), Book.is_preferred_edition.is_(False)
    ).all()
    return [r[0] for r in rows]


def search_chunks(qdrant: QdrantClient, query_vector: list, top_k: int,
                   source_filter=None, exclude_source_keys: list | None = None):
    """source_filter: None, a single source_key, or a list of source_keys
    to scope the search to (matches ANY of them). Always wins over the
    edition-preference exclusion -- naming books explicitly always wins,
    even if one of them is a non-preferred older edition."""
    sources = _normalize_sources(source_filter)
    must = []
    must_not = []

    if sources:
        match = MatchValue(value=sources[0]) if len(sources) == 1 else MatchAny(any=sources)
        must.append(FieldCondition(key="source", match=match))
    elif exclude_source_keys:
        must_not = [FieldCondition(key="source", match=MatchValue(value=k)) for k in exclude_source_keys]

    query_filter = Filter(must=must or None, must_not=must_not or None) if (must or must_not) else None
    result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
    )
    return result.points


def build_context_and_lookup(session: Session, hits) -> tuple[str, dict]:
    """Builds the LLM context block, and a lookup of apa_text -> RenderedCitation
    so <CITATION> tags in the answer can be resolved back to a Book afterward."""
    blocks = []
    lookup: dict[str, RenderedCitation] = {}
    book_cache: dict[str, Book | None] = {}

    for h in hits:
        payload = h.payload
        source_key = payload.get("source")
        if source_key not in book_cache:
            book_cache[source_key] = session.query(Book).filter_by(source_key=source_key).one_or_none()
        book = book_cache[source_key]

        rendered = render_citation(payload, book)
        lookup[rendered.apa_text] = rendered
        blocks.append(f"{rendered.tagged}\n{payload.get('text', '')}")

    return "\n\n---\n\n".join(blocks), lookup


def ask_llm(openai_client, question: str, context: str, model: str, history: str) -> str:
    response = openai_client.chat.completions.create(
        model=model,
        messages=_build_messages(question, context, history),
    )
    return response.choices[0].message.content


def ask_llm_stream(openai_client, question: str, context: str, model: str, history: str):
    """Generator yielding text deltas as the LLM produces them, instead of
    waiting for the full response. Used by the streaming API endpoint."""
    stream = openai_client.chat.completions.create(
        model=model,
        messages=_build_messages(question, context, history),
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _build_messages(question: str, context: str, history: str) -> list:
    system_prompt = (
        "You answer questions using only the provided book excerpts. Each "
        "excerpt is preceded by its citation wrapped in <CITATION></CITATION> "
        "tags. When you use information from an excerpt, copy its exact "
        "<CITATION>...</CITATION> tag immediately after the sentence that "
        "uses it -- do not alter the text inside the tags, paraphrase it, or "
        "invent new ones. If the excerpts don't contain enough information to "
        "answer, say so directly rather than guessing or using outside knowledge."
        "A user may ask out of topic questions, just say I do not know. Your answers should be scholarly."
        "You may get a history depending in a new chat or not, always scope your answer to the title if available"
        f"Here is the context of the history: {history}. The history is important for you to prevent hallucinations. For example a title can be about software development and user asks something irrelavnt, then answer according to scope , then restrict only to that field"
        "WHILST ANSWERING even with citations user the APA referencing in your statements."
        "ALWAYS CHECK FOR WORDS LIKE CONTINUE, PROCEED AS USER WOULD LIKE TO PROCEED WITH THEIR CHAT"
    )
    user_prompt = f"Excerpts:\n\n{context}\n\nQuestion: {question}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

def get_n_chat_messages_context(session: Session, chat_id: int | None, n_messages=3)-> str:
    if chat_id:
        chat = session.get(Chat, chat_id)
        if chat:
            # Query the n latest messages for this chat ordered by ID descending
            messages = session.query(Message)\
                .filter(Message.chat_id == chat_id)\
                .order_by(Message.id.desc())\
                .limit(n_messages)\
                .all()
            
            # Reverse to restore chronological order
            messages.reverse()
            
            # Build the context string for the LLM
            context_lines = []
            for msg in messages:
                context_lines.append(f"{msg.role}: {msg.content}")
            
            # Join the lines with a newline character
            llm_context_string = "\n".join(context_lines)
            
            return f"Chat Title: {chat.title}, History latest {n_messages}:{llm_context_string}"
            
    return "This is a new chat"


def get_or_create_chat(session: Session, chat_id: int | None, question: str,
                        user_id: int | None = None) -> Chat:
    if chat_id:
        chat = session.get(Chat, chat_id)
        if chat is None:
            raise ValueError(f"No chat with id {chat_id}")
        if user_id is not None and chat.user_id != user_id:
            raise PermissionError(f"Chat {chat_id} does not belong to this user")
        return chat
    title = question[:80] + ("..." if len(question) > 80 else "")
    chat = Chat(title=title, user_id=user_id)
    session.add(chat)
    session.flush()  # need chat.id before we can attach messages to it
    return chat


def save_turn(session: Session, chat: Chat, question: str, answer: str, citation_lookup: dict) -> Message:
    """Persists the user question and assistant answer as Messages, and
    every <CITATION> tag actually present in the answer as a Citation row
    linked to the assistant Message."""
    session.add(Message(chat_id=chat.id, role="user", content=question))

    assistant_message = Message(chat_id=chat.id, role="assistant", content=answer)
    session.add(assistant_message)
    session.flush()  # need assistant_message.id for the FK below

    for i, apa_text in enumerate(extract_citation_tags(answer)):
        rendered = citation_lookup.get(apa_text)
        session.add(Citation(
            message_id=assistant_message.id,
            book_id=rendered.book.id if rendered and rendered.book else None,
            apa_text=apa_text,
            locator=rendered.locator if rendered else None,
            order_index=i,
        ))

    session.flush()  # autoflush is off on this session -- without this,
                      # assistant_message.citations would appear empty to
                      # any code reading it before the session commits
    return assistant_message


def answer_question(
    session: Session,
    openai_client,
    qdrant: QdrantClient,
    question: str,
    chat_id: int | None = None,
    source_filter=None,
    top_k: int = DEFAULT_TOP_K,
    model: str = DEFAULT_CHAT_MODEL,
    all_editions: bool = False,
    user_id: int | None = None,
) -> dict:
    """End-to-end: retrieve, generate, persist. Returns a dict with the
    chat id, answer text, and the structured citations actually used --
    ready to hand to a frontend without it needing to parse the tags itself.

    source_filter: None, a single source_key, or a list of source_keys to
    scope the search to (matches ANY of them).

    By default, when a book has multiple editions in the library, only the
    preferred (normally latest) edition is searched, so an answer never
    silently blends content from a superseded edition. Pass
    all_editions=True to search every edition, or source_filter to pin
    specific files regardless of their preference."""
    chat = get_or_create_chat(session, chat_id, question, user_id=user_id)
    history = get_n_chat_messages_context(session=session, chat_id=chat_id)

    query_vector = embed_query(openai_client, question)
    exclude = [] if all_editions else get_excluded_source_keys(session)
    hits = search_chunks(qdrant, query_vector, top_k, source_filter, exclude_source_keys=exclude)

    if not hits:
        answer = "I couldn't find anything relevant to that question in the library."
        save_turn(session, chat, question, answer, {})
        return {"chat_id": chat.id, "answer": answer, "citations": []}

    context, citation_lookup = build_context_and_lookup(session, hits)
    answer = ask_llm(openai_client, question, context, model, history)
    assistant_message = save_turn(session, chat, question, answer, citation_lookup)

    citations_out = [
        {"apa_text": c.apa_text, "locator": c.locator, "book_id": c.book_id}
        for c in assistant_message.citations
    ]
    return {"chat_id": chat.id, "answer": answer, "citations": citations_out}


def answer_question_stream(
    session: Session,
    openai_client,
    qdrant: QdrantClient,
    question: str,
    chat_id: int | None = None,
    source_filter=None,
    top_k: int = DEFAULT_TOP_K,
    model: str = DEFAULT_CHAT_MODEL,
    all_editions: bool = False,
    user_id: int | None = None,
):
    """Generator version of answer_question. Yields (event_type, payload)
    tuples as the answer is generated:
      ("chat_id", 7)                          -- once, right away
      ("delta", "some text")                  -- repeatedly, as tokens arrive
      ("done", {"citations": [...]})          -- once, after the full answer
                                                  has been persisted

    Deliberately transport-agnostic (no SSE/HTTP formatting here) so this
    can be wired into Flask, a CLI, or anything else the same way."""
    chat = get_or_create_chat(session, chat_id, question, user_id=user_id)
    history = get_n_chat_messages_context(session=session, chat_id=chat_id)
    yield ("chat_id", chat.id)

    query_vector = embed_query(openai_client, question)
    exclude = [] if all_editions else get_excluded_source_keys(session)
    hits = search_chunks(qdrant, query_vector, top_k, source_filter, exclude_source_keys=exclude)

    if not hits:
        answer = "I couldn't find anything relevant to that question in the library."
        save_turn(session, chat, question, answer, {})
        yield ("delta", answer)
        yield ("done", {"citations": []})
        return

    context, citation_lookup = build_context_and_lookup(session, hits)

    full_answer_parts = []
    for delta in ask_llm_stream(openai_client, question, context, model, history):
        full_answer_parts.append(delta)
        yield ("delta", delta)

    answer = "".join(full_answer_parts)
    assistant_message = save_turn(session, chat, question, answer, citation_lookup)

    citations_out = [
        {"apa_text": c.apa_text, "locator": c.locator, "book_id": c.book_id}
        for c in assistant_message.citations
    ]
    yield ("done", {"citations": citations_out})
