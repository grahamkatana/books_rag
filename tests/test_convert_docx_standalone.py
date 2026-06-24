import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.verification import VerificationDocument
import app.ingestion.convert_docx as cd

original_convert_fn = cd.convert_docx_to_markdown

try:
    print("--- create_verification_document: row created, status uploaded ---")
    doc_id = cd.create_verification_document("test_create_verification_doc.docx", user_id=None)
    with get_session() as session:
        doc = session.get(VerificationDocument, doc_id)
        assert doc.status == "uploaded"
        assert doc.filename == "test_create_verification_doc.docx"
    print("OK")

    print("\n--- convert_uploaded_document: success path ---")
    with tempfile.TemporaryDirectory() as tmp:
        saved_path = Path(tmp) / "fake.docx"
        saved_path.write_bytes(b"fake docx bytes")
        cd.convert_docx_to_markdown = lambda path: "# Heading\n\nSome text."
        assert cd.convert_uploaded_document(doc_id, saved_path) is True
        with get_session() as session:
            doc = session.get(VerificationDocument, doc_id)
            assert doc.status == "extracting_claims"
            assert doc.markdown == "# Heading\n\nSome text."
            session.delete(doc)
    print("OK")

    print("\n--- convert_uploaded_document: conversion failure path ---")
    doc_id2 = cd.create_verification_document("test_convert_fail.docx", user_id=None)
    with tempfile.TemporaryDirectory() as tmp:
        saved_path = Path(tmp) / "fake.docx"
        saved_path.write_bytes(b"fake docx bytes")

        def raise_err(path):
            raise RuntimeError("simulated failure")

        cd.convert_docx_to_markdown = raise_err
        assert cd.convert_uploaded_document(doc_id2, saved_path) is False
        with get_session() as session:
            doc = session.get(VerificationDocument, doc_id2)
            assert doc.status == "failed"
            session.delete(doc)
    print("OK")

    print("\n--- convert_uploaded_document: nonexistent document_id ---")
    assert cd.convert_uploaded_document(999999, Path("/nonexistent")) is False
    print("OK")
finally:
    cd.convert_docx_to_markdown = original_convert_fn

print("\nAll standalone-function assertions passed.")