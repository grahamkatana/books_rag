"""
Single-command data ingestion: runs the full pipeline (report -> seed-books
-> chunk -> embed) in one shot.

This is a thin convenience wrapper around `python -m app.cli pipeline` --
identical behavior, just one file to point at directly instead of having
to remember the module path. All step sequencing, --force handling, and
error messages live in app/cli.py and are not duplicated here, so there's
exactly one place that logic can drift out of sync.

Usage:
    uv run python ingest.py
    uv run python ingest.py --force
"""

import sys

from app.cli import main as cli_main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "pipeline"] + sys.argv[1:]
    cli_main()
