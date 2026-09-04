# Ingestion into Qdrant

## How to ingest everything

Drop your PDFs into `pdfs/books/` and `pdfs/papers/`, then run:

```powershell
uv run python run_all.py          # starts Qdrant (local Docker), migrates DB, runs everything
uv run python -m app.cli pipeline           # books pipeline only
uv run python -m app.cli pipeline-papers    # papers pipeline only
```

The pipeline chunks each PDF into ~500-token pieces and upserts embeddings into Qdrant (`book_library` and `paper_library` collections). It's incremental — unchanged chunks are skipped (add `--force` to reprocess), so re-runs just pick up newly added files.

## API keys

| Key | Needed? |
|-----|---------|
| `OPENAI_API_KEY` | **Yes — mandatory.** Generates embeddings for Qdrant. |
| `QDRANT_API_KEY` | Only if connecting to Qdrant **Cloud**; local Docker (default) needs none. |
| `BRAVE_API_KEY` | No — optional. Without it, book bibliography lookup is skipped (papers use Crossref, no key). |

Copy `.env.example` to `.env` and fill in at minimum `OPENAI_API_KEY`. That's the only key required to complete ingestion. Optionally add `QDRANT_API_KEY` + set `QDRANT_URL` to your cloud endpoint if you're not using the local Docker container.