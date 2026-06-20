import sys, random
sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION
from app.db.session import get_session
from app.models.chat import Chat, Message, Citation
from app.retrieval.query_engine import answer_question


class FakeEmbeddingItem:
    def __init__(self, vector):
        self.embedding = vector

class FakeEmbeddingResponse:
    def __init__(self, vectors):
        self.data = [FakeEmbeddingItem(v) for v in vectors]

class FakeChoiceMessage:
    def __init__(self, content):
        self.content = content

class FakeChoice:
    def __init__(self, content):
        self.message = FakeChoiceMessage(content)

class FakeChatResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]

class FakeOpenAIClient:
    class embeddings:
        @staticmethod
        def create(model, input):
            vectors = [[random.random() for _ in range(EMBEDDING_DIM)] for _ in input]
            return FakeEmbeddingResponse(vectors)

    class chat:
        class completions:
            @staticmethod
            def create(model, messages):
                user_msg = messages[1]["content"]
                # Pull every <CITATION>...</CITATION> tag out of the prompt
                # context and echo them back, simulating an LLM that cites
                # correctly -- this is what we're really testing: that tags
                # surviving the round trip get parsed and persisted right.
                import re
                tags = re.findall(r"<CITATION>.*?</CITATION>", user_msg)
                body = "Software is delivered iteratively" + (tags[0] if len(tags) > 0 else "")
                body += ". Reference works are organized by entry" + (tags[1] if len(tags) > 1 else "")
                return FakeChatResponse(body)


qdrant = QdrantClient(":memory:")
qdrant.create_collection(QDRANT_COLLECTION, vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))

fixture_chunks = [
    {"chunk_id": "sommerville::1", "source": "Software-Engineering-9th-Edition-by-Ian-Sommerville",
     "text": "Agile methods emphasize iterative delivery and customer collaboration.",
     "printed_page": "46-47"},
    {"chunk_id": "gale::1", "source": "The-Gale-Encyclopedia-of-Medicine-3rd-Edition-staibabussalamsula_ac__id_",
     "text": "Entries in this encyclopedia are arranged alphabetically by topic.",
     "printed_page": "1"},
]
points = [
    PointStruct(id=i, vector=[random.random() for _ in range(EMBEDDING_DIM)], payload=c)
    for i, c in enumerate(fixture_chunks)
]
qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)

fake_openai = FakeOpenAIClient()

with get_session() as session:
    result1 = answer_question(
        session, fake_openai, qdrant,
        question="How are software methods typically delivered?",
        top_k=2,
    )
    print("--- first turn ---")
    print("chat_id:", result1["chat_id"])
    print("answer:", result1["answer"])
    print("citations:", result1["citations"])

    # Second turn in the SAME chat, to confirm chat continuity works
    result2 = answer_question(
        session, fake_openai, qdrant,
        question="And how are reference works organized?",
        chat_id=result1["chat_id"],
        top_k=2,
    )
    print("\n--- second turn (same chat) ---")
    print("chat_id:", result2["chat_id"], "(should match first)")
    print("answer:", result2["answer"])

with get_session() as session:
    chat = session.get(Chat, result1["chat_id"])
    print(f"\n--- persisted chat '{chat.title}' has {len(chat.messages)} messages ---")
    for m in chat.messages:
        print(f"  [{m.role}] {m.content[:80]}")
        for c in m.citations:
            print(f"      citation -> book_id={c.book_id} locator={c.locator!r} apa={c.apa_text!r}")
