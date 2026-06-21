import sys, csv
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import extract_isbns as ei
from app.config import PDF_DIR

# --- checksum validation, against canonical known-correct ISBNs (the
# classic Wikipedia ISBN-article example), not just made-up numbers ---

assert ei.is_valid_isbn10("0306406152") is True
assert ei.is_valid_isbn13("9780306406157") is True

# Mutate one digit -- must now fail
assert ei.is_valid_isbn10("0306406151") is False
assert ei.is_valid_isbn13("9780306406158") is False

# ISBN-10 with an "X" check digit -- a real, well-known example
assert ei.is_valid_isbn10("097522980X") is True

# Plausible-looking but NOT a real ISBN -- must be rejected, since the
# whole point of checksum validation is to reject exactly this
assert ei.is_valid_isbn13("1234567890123") is False
assert ei.is_valid_isbn10("1234567890") is False

# Wrong length / non-digit content -- shouldn't even reach the checksum math
assert ei.is_valid_isbn13("97803064061") is False  # too short
assert ei.is_valid_isbn10("03064061XX") is False   # two check-digit-looking chars

print("Checksum validation assertions passed.")

# --- find_isbns_in_text, on realistic copyright-page-style text ---

text = """
Copyright (c) 2011 Pearson Education
ISBN-13: 978-0-306-40615-7
ISBN-10: 0-306-40615-2
Printed in the United States of America
"""
found = ei.find_isbns_in_text(text)
assert found == {"9780306406157", "0306406152"}, f"unexpected: {found}"

# Bare ISBN-13 with no "ISBN" label nearby (e.g. barcode text) should
# still be found via the fallback pattern
bare_text = "  9 780306 406157  some barcode-adjacent text"
found_bare = ei.find_isbns_in_text(bare_text)
assert "9780306406157" in found_bare, f"bare ISBN-13 fallback didn't match: {found_bare}"

# Plain prose with plausible-looking numbers but no real ISBN should
# find nothing
clean_text = "See page 9780306 for more on chapter 406157 of this 13-part series."
assert ei.find_isbns_in_text(clean_text) == set()

print("find_isbns_in_text assertions passed.")

# --- pages_to_scan window logic ---

assert ei.pages_to_scan(num_pages=100, front=30, back=10, full=False) == list(range(30)) + list(range(90, 100))
assert ei.pages_to_scan(num_pages=20, front=30, back=10, full=False) == list(range(20)), \
    "a book shorter than the front window should just scan everything once, not error or duplicate"
assert ei.pages_to_scan(num_pages=100, front=30, back=10, full=True) == list(range(100))

print("pages_to_scan window-logic assertions passed.")

# --- error handling: a corrupted/non-PDF file shouldn't crash the batch ---

import tempfile
with tempfile.TemporaryDirectory() as tmp:
    fake_pdf = Path(tmp) / "not_really_a_pdf.pdf"
    fake_pdf.write_text("this is not a pdf")
    result = ei.process_pdf(fake_pdf, front=30, back=10, full=False)
    assert result["error"], "a corrupted PDF should produce a row with an error, not raise"
    assert result["all_isbns_found"] == ""
    assert result["file_name"] == "not_really_a_pdf.pdf"

print("Corrupted-file handling assertions passed.")

# --- full pipeline: main() writes a well-formed CSV ---

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / "fake_one.pdf").write_text("not a real pdf, just exercising the error path")
    output_csv = tmp_path / "out.csv"

    original_pdf_dir = ei.PDF_DIR
    ei.PDF_DIR = tmp_path
    try:
        ei.main(output_csv, front=30, back=10, full=False)
    finally:
        ei.PDF_DIR = original_pdf_dir

    assert output_csv.exists()
    with open(output_csv) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["file_name"] == "fake_one.pdf"
    assert rows[0]["error"]  # this fake file can't actually be read as a PDF

print("main() end-to-end CSV-writing assertions passed.")

# --- integration check against a real book, if one happens to be
# present locally. Correctly never committed to this repo (copyright),
# so skip cleanly rather than fail when it's absent -- same pattern as
# this project's other tests that need a real PDF. ---

SOMMERVILLE = PDF_DIR / "Software-Engineering-9th-Edition-by-Ian-Sommerville.pdf"
if SOMMERVILLE.exists():
    result = ei.process_pdf(SOMMERVILLE, front=30, back=10, full=False)
    print(f"\n[real PDF] Sommerville -> isbn_13={result['isbn_13']!r} "
          f"all_found={result['all_isbns_found']!r}")
    assert not result["error"]
    assert result["all_isbns_found"], "expected at least one real ISBN to be found in this book"
else:
    print(f"\n[skip] {SOMMERVILLE.name} not present (expected in CI -- copyrighted book PDFs "
          f"aren't committed). This check needs it locally to run for real.")

print("\nAll extract_isbns assertions passed.")