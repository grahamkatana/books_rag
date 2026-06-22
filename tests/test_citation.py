import sys
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.chat import Chat, Message, Citation
from app.models.book import Book
from app.models.paper import Paper

BOOK_KEY = "test_citation_paper_id_book"
PAPER_KEY = "test_citation_paper_id_paper"

with get_session() as session:
    existing_book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
    if existing_book is not None:
        session.delete(existing_book)
    existing_paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
    if existing_paper is not None:
        session.delete(existing_paper)

with get_session() as session:
    book = Book(source_key=BOOK_KEY, title="A Test Book", year=2020, bibliography_verified=True, page_mode="labeled")
    paper = Paper(source_key=PAPER_KEY, title="A Test Paper", year=2026)
    chat = Chat(title="Test chat")
    session.add_all([book, paper, chat])
    session.flush()
    msg = Message(chat_id=chat.id, role="assistant", content="An answer citing both a book and a paper.")
    session.add(msg)
    session.flush()

    # The exact scenario that motivated keeping one shared Citation
    # table instead of a separate PaperCitation model: a single answer
    # citing both corpora, where order_index must reflect the true order
    # they appeared in, not be split across two tables to merge later.
    session.add(Citation(message_id=msg.id, book_id=book.id, apa_text="(Test, 2020, p. 5)", order_index=0))
    session.add(Citation(message_id=msg.id, paper_id=paper.id, apa_text="(Test, 2026)", order_index=1))
    session.add(Citation(message_id=msg.id, book_id=None, paper_id=None, apa_text="(Unresolved, n.d.)", order_index=2))
    session.flush()
    msg_id = msg.id

try:
    with get_session() as session:
        msg = session.get(Message, msg_id)
        citations = msg.citations

        assert len(citations) == 3
        assert citations[0].order_index == 0
        assert citations[0].book.title == "A Test Book"
        assert citations[0].paper is None

        assert citations[1].order_index == 1
        assert citations[1].paper.title == "A Test Paper"
        assert citations[1].book is None

        assert citations[2].order_index == 2
        assert citations[2].book is None and citations[2].paper is None, \
            "an unresolved citation should have neither FK set, not crash on a missing relationship"

    print("All Citation paper_id assertions passed.")
finally:
    with get_session() as session:
        chat = session.query(Chat).filter(Chat.title == "Test chat").one_or_none()
        if chat is not None:
            session.delete(chat)  # cascades to Message -> Citation
        book = session.query(Book).filter_by(source_key=BOOK_KEY).one_or_none()
        if book is not None:
            session.delete(book)
        paper = session.query(Paper).filter_by(source_key=PAPER_KEY).one_or_none()
        if paper is not None:
            session.delete(paper)