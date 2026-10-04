"""Regression test: an LLM answer that echoes a NUL (0x00) byte from an
ingested chunk must persist, not blow up.

~6% of ingested chunks carry NUL bytes (PDF extraction). The LLM echoes them
into its answer, and PostgreSQL rejects text columns containing NUL with
psycopg.DataError ("PostgreSQL text fields cannot contain NUL (0x00) bytes")
-- after the answer has already streamed to the client, which is what shows up
as "sorry, could not answer". save_turn must strip NUL bytes at the persistence
boundary so the turn lands regardless of what the LLM emitted."""
import os
import sys
import tempfile

sys.path.insert(0, ".")

# Isolated temp DB -- never touches the dev's real book_rag.db, and no
# alembic migration needed (create_all builds the schema from the models).
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from app.models import Base  # noqa: E402  (imports all tables onto Base.metadata)
from app.models.chat import Chat, Message  # noqa: E402
from app.db.session import engine, get_session  # noqa: E402
from app.retrieval.query_engine import save_turn  # noqa: E402

Base.metadata.create_all(engine)

answer = "Agile methods emphasize iterative delivery.\x00 and customer collaboration."

with get_session() as session:
    chat = Chat(title="nul sanitization", user_id=None)
    session.add(chat)
    session.flush()  # assign chat.id before save_turn references it
    save_turn(session, chat, "How are software methods delivered?", answer, {})
    chat_id = chat.id  # capture before the session closes/expires the object

with get_session() as session:
    msg = session.query(Message).filter_by(chat_id=chat_id, role="assistant").one()
    assert msg is not None, "assistant message was not persisted"
    assert "\x00" not in msg.content, f"NUL byte survived into the DB: {msg.content!r}"

os.unlink(_tmp.name)
print("NUL-byte sanitization test passed.")
