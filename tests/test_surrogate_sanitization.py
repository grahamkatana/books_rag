import sys, re
sys.path.insert(0, ".")

from app.ingestion.chunk_trusted_books import sanitize_text, chunk_book


class MockWordEncoder:
    # Add *args and **kwargs to catch tiktoken-specific configurations gracefully
    def encode(self, text, *args, **kwargs):
        return list(re.finditer(r"\S+|\s+", text))

    def decode_single_token_bytes(self, token):
        return token.group(0).encode("utf-8")


# \ud835 is a real crash this project hit in production: a lone UTF-16
# surrogate from a math-heavy PDF ("Generative Deep Learning") whose font
# encoding pypdf mis-decoded. UTF-8 can't represent a lone surrogate at
# all, so this used to crash the whole chunking pipeline over one book.
bad_text = "The gradient \ud835 with respect to weights is computed via backprop."

clean = sanitize_text(bad_text)
assert "\ud835" not in clean, "sanitize_text should strip lone surrogates"

# Should not raise -- this is the exact line that used to crash
clean.encode("utf-8")

# Full pipeline: a page containing this text should chunk without crashing
pages = [{
    "page_index": 0,
    "label": "1",
    "text": clean,
    "start_byte": 0,
    "end_byte": len(clean.encode("utf-8")),
}]
chunks = chunk_book(pages, encoder=MockWordEncoder())
assert len(chunks) == 1
assert "\ud835" not in chunks[0]["text"]

print("Lone-surrogate sanitization regression test passed.")
