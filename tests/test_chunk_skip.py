import sys, re
sys.path.insert(0, ".")

import pandas as pd
import tiktoken
import app.ingestion.chunk_trusted_books as ctb
from app.config import REPORT_PATH, PDF_DIR

BOOK = "Software-Engineering-9th-Edition-by-Ian-Sommerville"

# This test exercises real PDF text extraction, which needs the actual
# (copyrighted) book file -- correctly never committed to this repo. In
# CI, where it won't be present, skip cleanly rather than fail on a
# fixture this test was never meant to have.
if not (PDF_DIR / f"{BOOK}.pdf").exists():
    print(f"[skip] {BOOK}.pdf not present (expected in CI -- copyrighted book "
          f"PDFs aren't committed). This test needs it locally to run for real.")
    sys.exit(0)


class MockWordEncoder:
    def encode(self, text):
        return list(re.finditer(r"\S+|\s+", text))

    def decode_single_token_bytes(self, token):
        return token.group(0).encode("utf-8")


tiktoken.get_encoding = lambda name: MockWordEncoder()

out_path = ctb.CHUNKS_DIR / f"{BOOK}.jsonl"

# Scope report.csv down to just this one book for the test. The mock
# encoder's pure-Python regex tokenization is fine for a 790-page book but
# would be painfully slow against a 4500+ page encyclopedia if that also
# happens to be sitting in pdfs/books/ -- real tiktoken (Rust-backed)
# doesn't have this problem, this is purely a test-fixture concern.
original_report = pd.read_csv(REPORT_PATH)
original_report[original_report["file_name"] == f"{BOOK}.pdf"].to_csv(REPORT_PATH, index=False)

try:
    # force a fresh start for this test regardless of leftover state from
    # other tests/manual runs earlier in the session
    if out_path.exists():
        out_path.unlink()

    print("=== Run 1: fresh run should process ===")
    ctb.main(force=False)
    assert out_path.exists()
    first_mtime = out_path.stat().st_mtime
    first_size = out_path.stat().st_size

    print("\n=== Run 2: unchanged file/settings should skip entirely ===")
    ctb.main(force=False)
    assert out_path.stat().st_mtime == first_mtime, "file should not have been rewritten on an unchanged run"

    print("\n=== Run 3: --force should reprocess even though nothing changed ===")
    ctb.main(force=True)
    assert out_path.stat().st_size == first_size  # deterministic chunking -> same content

    print("\nAll trusted-book chunk-skip assertions passed.")
finally:
    original_report.to_csv(REPORT_PATH, index=False)
