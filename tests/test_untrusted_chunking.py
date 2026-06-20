import sys, re
sys.path.insert(0, ".")

import pdfplumber
from app.config import PDF_DIR
import app.ingestion.chunk_untrusted_books as cub

PDF_PATH = PDF_DIR / "_OceanofPDF_com_Risk-First_Software_Development_2E_-_Rob_Moffat.pdf"

# This test exercises real font-size heading detection against actual
# book content, which needs the real (copyrighted) PDF -- correctly never
# committed to this repo. Skip cleanly in CI rather than fail on a
# fixture this test was never meant to have.
if not PDF_PATH.exists():
    print(f"[skip] {PDF_PATH.name} not present (expected in CI -- copyrighted "
          f"book PDFs aren't committed). This test needs it locally to run for real.")
    sys.exit(0)


class MockWordEncoder:
    """Whitespace-based stand-in for tiktoken, used the same way as in
    the trusted-book chunking tests -- avoids needing network access to
    download cl100k_base just to validate the chunking logic itself."""
    def encode(self, text):
        return list(re.finditer(r"\S+|\s+", text))

    def decode_single_token_bytes(self, token):
        return token.group(0).encode("utf-8")


with pdfplumber.open(str(PDF_PATH)) as pdf:
    body_size = cub.find_body_text_size(pdf)
    pages = cub.extract_pages_with_headings(pdf, body_size)

print(f"Detected body text size: {body_size}pt (threshold: {round(body_size * cub.HEADING_SIZE_RATIO, 2)}pt)")

# These are the exact headings confirmed by hand earlier in this project --
# both the chapter-level ones and, critically, the ~12%-larger subsection
# heading ("Stage 1: Specification") that a too-high threshold would miss.
expected = {
    17: "Introduction",
    18: "Positioning Risk-First Software Development",
    19: "Background to the First Edition: A Quick History",
    50: "Applying the Toy Process",
    52: "Stage 1: Specification",
    200: "Dependency Risks",
}

for page_idx, expected_heading in expected.items():
    actual = pages[page_idx]["heading_at_start"]
    assert actual == expected_heading, (
        f"page {page_idx}: expected {expected_heading!r}, got {actual!r}"
    )
    print(f"  page {page_idx}: {actual!r} -- OK")

# Front matter before any heading is detected should be None, not some
# leftover/garbage value
assert pages[0]["heading_at_start"] is None

# Full chunking pass with the mock encoder, then confirm a chunk that we
# know falls inside "Stage 1: Specification" actually carries that
# chapter in its output record, and that the locator/citation built from
# it looks right end to end.
cub.CHUNK_SIZE_TOKENS = 200  # smaller, for a quicker test with the mock word-encoder
cub.CHUNK_OVERLAP_TOKENS = 20
chunks = cub.chunk_book(pages[:60], encoder=MockWordEncoder())

stage1_chunks = [c for c in chunks if c["chapter"] == "Stage 1: Specification"]
assert stage1_chunks, "expected at least one chunk tagged with the Stage 1: Specification heading"
print(f"\n{len(stage1_chunks)} chunk(s) correctly tagged with 'Stage 1: Specification'")

from app.retrieval.citations import build_locator
locator = build_locator(stage1_chunks[0])
print("Locator built from that chunk:", locator)
assert locator.startswith('"Stage 1: Specification" section, approx. PDF p.')

print("\nAll untrusted-book chunking assertions passed.")
