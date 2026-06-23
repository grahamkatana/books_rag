"""
Shared client singletons for the API layer, constructed lazily so
importing this module (and therefore the whole app) never fails just
because OPENAI_API_KEY isn't set yet -- the failure happens on first real
use instead, which is also easier to test against with fakes.
"""

from openai import OpenAI
from qdrant_client import QdrantClient

from app.config import QDRANT_URL, QDRANT_API_KEY, QDRANT_TIMEOUT

_openai_client: OpenAI | None = None
_qdrant_client: QdrantClient | None = None


def get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=QDRANT_TIMEOUT)
    return _qdrant_client