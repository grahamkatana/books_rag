"""
Centralized configuration. Everything reads from here instead of calling
os.environ directly, so there's one place to see every setting this app
depends on.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Database
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'book_rag.db'}")

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "3072"))
DEFAULT_CHAT_MODEL = os.environ.get("DEFAULT_CHAT_MODEL", "gpt-5.4-mini")

# Brave Search (used for automatic bibliography lookup -- optional, see
# app/ingestion/lookup_bibliography.py. Without this set, that step is
# skipped and seed_books.py falls back to its filename heuristic.)
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")

# Qdrant
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "book_library")

# Paths
PDF_DIR = BASE_DIR / "pdfs" / "books"
DATA_DIR = BASE_DIR / "data"
REPORT_PATH = DATA_DIR / "report.csv"
CHUNKS_DIR = DATA_DIR / "chunks"

# Chunking
CHUNK_SIZE_TOKENS = int(os.environ.get("CHUNK_SIZE_TOKENS", "500"))
CHUNK_OVERLAP_TOKENS = int(os.environ.get("CHUNK_OVERLAP_TOKENS", "75"))

# Retrieval
DEFAULT_TOP_K = int(os.environ.get("DEFAULT_TOP_K", "6"))

# Auth -- JWT secret for the API, session secret for the Flask-Admin
# panel. Generate real values before deploying anywhere beyond your own
# machine: `python -c "import secrets; print(secrets.token_hex(32))"`
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-insecure-jwt-secret-change-me")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-flask-secret-change-me")

LOG_DIR = BASE_DIR / os.environ.get("LOG_DIR", "logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))