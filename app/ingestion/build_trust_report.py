"""
Scans every PDF in pdfs/books/, checks whether it has genuine embedded
page-label metadata, and writes data/report.csv flagging which books can
be cited by exact page number vs which need the chapter/heading-based
fallback instead.

Usage:
    python -m app.ingestion.build_trust_report
"""

from pathlib import Path
import pandas as pd
from pypdf import PdfReader

from app.config import PDF_DIR, REPORT_PATH, DATA_DIR


def check_page_labels(pdf_path: Path) -> dict:
    row = {
        "file_name": pdf_path.name,
        "total_pages": None,
        "has_page_labels": False,
        "trust_page_numbers": False,
        "first_labels": None,
        "last_labels": None,
        "notes": "",
    }
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        row["notes"] = f"could not open file: {e}"
        return row

    try:
        total_pages = len(reader.pages)
        row["total_pages"] = total_pages
    except Exception as e:
        row["notes"] = f"could not read page count: {e}"
        return row

    try:
        root = reader.trailer["/Root"]
        has_labels = "/PageLabels" in root
        row["has_page_labels"] = has_labels
    except Exception as e:
        row["notes"] = f"could not read PDF catalog: {e}"
        return row

    if not has_labels:
        row["trust_page_numbers"] = False
        row["notes"] = (
            "no /PageLabels in catalog -- this book has no real printed "
            "page numbers to extract; use chapter/heading + approximate "
            "physical page index for citations instead"
        )
        return row

    try:
        labels = reader.page_labels
        if not labels or len(labels) != total_pages:
            row["trust_page_numbers"] = False
            row["notes"] = (
                "/PageLabels present but label count doesn't match page "
                "count -- inspect this one manually before trusting it"
            )
        else:
            row["trust_page_numbers"] = True
            row["first_labels"] = ", ".join(labels[:5])
            row["last_labels"] = ", ".join(labels[-5:])
            row["notes"] = "embedded page labels found and look valid"
    except Exception as e:
        row["trust_page_numbers"] = False
        row["notes"] = f"error reading labels: {e}"

    return row


def main():
    if not PDF_DIR.exists():
        raise SystemExit(f"Folder not found: {PDF_DIR}. Create it and drop your book PDFs in there.")

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        raise SystemExit(f"No PDFs found in {PDF_DIR}.")

    rows = [check_page_labels(p) for p in pdf_files]
    df = pd.DataFrame(rows)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(REPORT_PATH, index=False)

    print(df[["file_name", "total_pages", "trust_page_numbers", "notes"]].to_string(index=False))
    print(f"\nReport written to {REPORT_PATH.resolve()}")


if __name__ == "__main__":
    main()
