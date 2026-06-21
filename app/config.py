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
# Deliberately separate from QDRANT_COLLECTION -- papers and books never
# share a collection, so a retrieval call for one corpus can't possibly
# surface noise from the other regardless of which code path runs it.
PAPERS_QDRANT_COLLECTION = os.environ.get("PAPERS_QDRANT_COLLECTION", "paper_library")

# Paths
PDF_DIR = BASE_DIR / "pdfs" / "books"
DATA_DIR = BASE_DIR / "data"
REPORT_PATH = DATA_DIR / "report.csv"
CHUNKS_DIR = DATA_DIR / "chunks"

# Paper paths -- same shape as the book paths above, under their own
# "papers" subfolder of each, so the two pipelines' generated files
# (report.csv, chunk .jsonl files) never collide or get confused for
# each other on disk, the same way their Qdrant collections don't.
PAPER_PDF_DIR = BASE_DIR / "pdfs" / "papers"
PAPERS_DATA_DIR = DATA_DIR / "papers"
PAPERS_REPORT_PATH = PAPERS_DATA_DIR / "report.csv"
PAPERS_CHUNKS_DIR = PAPERS_DATA_DIR / "chunks"

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

# Logging -- JSON, rotating file (for Promtail/Loki/Grafana to read) plus
# plain-text console output (for `docker compose logs` / local terminal).
LOG_DIR = BASE_DIR / os.environ.get("LOG_DIR", "logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB per file
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))  # keep 5 old files beyond the current one

# Crossref (used for paper bibliography lookup -- see
# app/ingestion/lookup_paper_doi.py). No API key exists or is needed;
# Crossref's own docs explicitly encourage including real contact info
# via this "polite pool" parameter for more reliable rate-limit
# treatment. Entirely optional -- lookups work without it.
CROSSREF_MAILTO = os.environ.get("CROSSREF_MAILTO")