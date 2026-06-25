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

# Used by app/agents/cross_check_claim.py -- an independent second
# opinion on a claim verification, deliberately from a different model
# provider than the primary verification agent (which uses
# DEFAULT_CHAT_MODEL via OpenAI). Two same-provider models share
# correlated blind spots; a genuinely different model is a meaningfully
# stronger check on the same reasoning.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CROSS_CHECK_MODEL = os.environ.get("CROSS_CHECK_MODEL", "claude-sonnet-4-6")

# Brave Search (used for automatic bibliography lookup -- optional, see
# app/ingestion/lookup_bibliography.py. Without this set, that step is
# skipped and seed_books.py falls back to its filename heuristic.)
BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY")

# Qdrant
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
# qdrant-client's own default (effectively a handful of seconds, via
# httpx) is short enough that a filtered operation against a real,
# grown library can exceed it -- confirmed in practice: delete_book's
# count-before-delete step timed out against a production-sized
# collection. 30s is a deliberately generous margin, not a tuned value.
QDRANT_TIMEOUT = int(os.environ.get("QDRANT_TIMEOUT", "30"))
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

# Redis / Celery -- used by app/worker/* to run admin operations (book/
# paper deletion, for now) as background jobs instead of blocking an API
# request for however long the operation takes. Broker and result
# backend both default to the same Redis instance since there's no
# reason to run two separate ones for a project this size; override
# independently if that ever changes.
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "0")

# Built from the pieces above only when REDIS_URL itself isn't set
# directly -- if a password is configured, it has to actually be in the
# URL or every connection gets rejected with NOAUTH the moment the
# Redis side starts requiring one (confirmed directly: an unauthenticated
# connection to a --requirepass instance fails immediately, it doesn't
# degrade gracefully). No password configured falls back to the
# original no-auth URL, unchanged from before this existed.
if REDIS_PASSWORD:
    _default_redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    _default_redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

REDIS_URL = os.environ.get("REDIS_URL", _default_redis_url)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

# Where uploaded .docx files for the verification feature get saved,
# the same "keep the real source file around" philosophy as pdfs/books/
# and pdfs/papers/ -- not strictly required for the pipeline to run (the
# markdown it produces is what everything downstream actually uses), but
# useful for debugging a bad conversion or re-running it later without
# asking the user to re-upload.
VERIFICATION_UPLOADS_DIR = BASE_DIR / "data" / "verification_uploads"