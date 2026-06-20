"""
Single-command bootstrap for the whole ingestion workflow: starts Qdrant
(via docker compose, if it looks like a local instance), makes sure the
database schema is current, then runs report -> seed-books -> chunk ->
embed -- so dropping a new PDF into pdfs/books/ and running this one
command is enough to make it queryable.

Place this at the project root, next to server.py and pyproject.toml.

Usage:
    uv run python run_all.py
    uv run python run_all.py --force          # bypass chunk/embed's unchanged-skip cache
    uv run python run_all.py --skip-qdrant    # don't try to start Qdrant yourself
"""

import argparse
import subprocess
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def start_qdrant(qdrant_url: str) -> None:
    print("=== Starting Qdrant ===")

    if "localhost" not in qdrant_url and "127.0.0.1" not in qdrant_url:
        print(f"  QDRANT_URL ({qdrant_url}) doesn't look local -- assuming it's "
              f"already running somewhere (e.g. Qdrant Cloud) and skipping docker compose.")
        return

    try:
        subprocess.run(["docker", "compose", "up", "-d", "qdrant"], check=True, cwd=PROJECT_ROOT)
    except FileNotFoundError:
        print("  docker not found on PATH -- skipping. Make sure Qdrant is reachable some other way.")
        return
    except subprocess.CalledProcessError as e:
        print(f"  docker compose failed ({e}) -- continuing anyway in case Qdrant is already up.")
        return

    for _ in range(15):
        try:
            urllib.request.urlopen(qdrant_url, timeout=1)
            print("  Qdrant is reachable.")
            return
        except Exception:
            time.sleep(1)
    print("  Warning: Qdrant didn't respond after 15s -- continuing anyway, embed may fail.")


def run_migrations() -> None:
    print("\n=== Applying database migrations ===")
    subprocess.run(["alembic", "upgrade", "head"], check=True, cwd=PROJECT_ROOT)


def run_pipeline(force: bool) -> None:
    print("\n=== Running ingestion pipeline ===")
    from app.ingestion.build_trust_report import main as build_report
    from app.ingestion.seed_books import main as seed_books
    from app.ingestion.chunk_trusted_books import main as chunk_books
    from app.ingestion.embed_upload import main as embed_books

    steps = [
        ("report", lambda: build_report()),
        ("seed-books", lambda: seed_books()),
        ("chunk", lambda: chunk_books(force=force)),
        ("embed", lambda: embed_books(force=force)),
    ]
    for i, (name, fn) in enumerate(steps, start=1):
        print(f"\n--- Step {i}/{len(steps)}: {name} ---")
        fn()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the whole book-rag pipeline in one command.")
    parser.add_argument("--force", action="store_true",
                         help="Reprocess every book in chunk/embed, ignoring the unchanged-skip cache")
    parser.add_argument("--skip-qdrant", action="store_true",
                         help="Don't try to start Qdrant via docker compose yourself")
    args = parser.parse_args()

    from app.config import QDRANT_URL

    if not args.skip_qdrant:
        start_qdrant(QDRANT_URL)

    run_migrations()
    run_pipeline(force=args.force)

    print("\n=== All done -- the library is ready to query ===")
    print('Try:  uv run python -m app.cli ask "What is software engineering?"')
    print("Or start the API:  uv run python server.py")


if __name__ == "__main__":
    main()
