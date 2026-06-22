"""
Single-command papers ingestion: runs the full papers pipeline
(seed-papers -> lookup-paper-doi -> chunk-papers -> embed-papers) in one
shot.

This is a thin convenience wrapper around `python -m app.cli pipeline-papers`
-- identical behavior, just one file to point at directly instead of
having to remember the module path. All step sequencing, --force
handling, and error messages live in app/cli.py and are not duplicated
here, so there's exactly one place that logic can drift out of sync --
the same reasoning ingest.py already follows for the books pipeline.

Requires docling to be installed first (see README) -- chunk-papers will
fail with a clear message rather than a crash if it isn't, but every
step before it will still run normally.

Usage:
    uv run python ingest_papers.py
    uv run python ingest_papers.py --force
"""

import sys

from app.cli import main as cli_main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "pipeline-papers"] + sys.argv[1:]
    cli_main()