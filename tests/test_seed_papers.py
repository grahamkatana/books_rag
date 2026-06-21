import sys
sys.path.insert(0, ".")

from app.ingestion import seed_papers
from app.db.session import get_session
from app.models.paper import Paper

assert seed_papers.guess_title_from_filename("Becker-et-al-2026_Evolving-With-AI") == "Becker et al 2026 Evolving With AI"
assert seed_papers.guess_title_from_filename("simple") == "simple"
print("guess_title_from_filename assertions passed.")

import tempfile
from pathlib import Path

KEY = "test_seed_papers_new_paper"

with get_session() as session:
    existing = session.query(Paper).filter_by(source_key=KEY).one_or_none()
    if existing is not None:
        session.delete(existing)

with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    (tmp_path / f"{KEY}.pdf").write_bytes(b"not a real pdf, just exercising the glob + filename logic")

    original_dir = seed_papers.PAPER_PDF_DIR
    seed_papers.PAPER_PDF_DIR = tmp_path
    try:
        seed_papers.main()  # should create exactly one new row
        seed_papers.main()  # running again should change nothing -- existing row left alone
    finally:
        seed_papers.PAPER_PDF_DIR = original_dir

with get_session() as session:
    paper = session.query(Paper).filter_by(source_key=KEY).one()
    assert paper.title == "test seed papers new paper"
    assert paper.bibliography_verified is False
    assert paper.bibliography_source == "filename_guess"
    session.delete(paper)

print("main() end-to-end assertions passed (creates once, leaves alone on rerun).")
print("\nAll seed_papers assertions passed.")