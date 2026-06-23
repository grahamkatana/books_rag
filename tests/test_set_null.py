import sys
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.user import User
from app.models.book import Book
from app.models.paper import Paper
from app.models.chat import Chat, Message, Citation
from app.auth.security import hash_password

BOOK_KEY = "test_setnull_book"
PAPER_KEY = "test_setnull_paper"
USER_EMAIL = "test_setnull_user@example.com"

with get_session() as session:
    for cls, key in [(Book, BOOK_KEY), (Paper, PAPER_KEY)]:
        row = session.query(cls).filter_by(source_key=key).one_or_none()
        if row is not None:
            session.delete(row)
    existing_user = session.query(User).filter_by(email=USER_EMAIL).one_or_none()
    if existing_user is not None:
        session.delete(existing_user)

print("--- deleting a Book with an existing citation: citation survives, book_id nulls out ---")
with get_session() as session:
    book = Book(source_key=BOOK_KEY, title="SetNull Test Book", year=2020,
                bibliography_verified=True, page_mode="labeled")
    session.add(book)
    session.flush()
    chat = Chat(title="setnull book test chat")
    session.add(chat)
    session.flush()
    msg = Message(chat_id=chat.id, role="assistant", content="cites a book")
    session.add(msg)
    session.flush()
    session.add(Citation(message_id=msg.id, book_id=book.id, apa_text="(SetNull Test, 2020)", order_index=0))
    book_id, msg_id, chat_id_book = book.id, msg.id, chat.id

with get_session() as session:
    session.delete(session.get(Book, book_id))

with get_session() as session:
    msg = session.get(Message, msg_id)
    citation = msg.citations[0]
    assert citation.book_id is None, "deleting the book should null out the citation's book_id"
    assert citation.apa_text == "(SetNull Test, 2020)", "the citation itself must survive untouched"
    assert session.get(Chat, chat_id_book) is not None, "the chat must absolutely still exist"
print("OK")

print("\n--- deleting a Paper with an existing citation: same behavior ---")
with get_session() as session:
    paper = Paper(source_key=PAPER_KEY, title="SetNull Test Paper", year=2026)
    session.add(paper)
    session.flush()
    chat = Chat(title="setnull paper test chat")
    session.add(chat)
    session.flush()
    msg = Message(chat_id=chat.id, role="assistant", content="cites a paper")
    session.add(msg)
    session.flush()
    session.add(Citation(message_id=msg.id, paper_id=paper.id, apa_text="(SetNull Test, 2026)", order_index=0))
    paper_id, msg_id_paper = paper.id, msg.id

with get_session() as session:
    session.delete(session.get(Paper, paper_id))

with get_session() as session:
    msg = session.get(Message, msg_id_paper)
    citation = msg.citations[0]
    assert citation.paper_id is None
    assert citation.apa_text == "(SetNull Test, 2026)"
print("OK")

print("\n--- deleting a User with an existing chat: chat survives, orphaned (user_id nulls out) ---")
with get_session() as session:
    user = User(email=USER_EMAIL, password_hash=hash_password("testpass123"), is_admin=False)
    session.add(user)
    session.flush()
    chat = Chat(title="setnull user test chat", user_id=user.id)
    session.add(chat)
    session.flush()
    user_id, chat_id_user = user.id, chat.id

with get_session() as session:
    session.delete(session.get(User, user_id))

with get_session() as session:
    chat = session.get(Chat, chat_id_user)
    assert chat is not None, "deleting the user must not delete their chat history"
    assert chat.user_id is None, "the chat should be orphaned, same as a CLI-created chat"
print("OK")

with get_session() as session:
    for chat_title in ("setnull book test chat", "setnull paper test chat", "setnull user test chat"):
        chat = session.query(Chat).filter_by(title=chat_title).one_or_none()
        if chat is not None:
            session.delete(chat)

print("\nAll SET NULL regression assertions passed.")