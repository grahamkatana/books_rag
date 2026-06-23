import sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")

from app.db.session import get_session
from app.models.verification import VerificationDocument
import app.ingestion.convert_docx as cd

original_uploads_dir = cd.VERIFICATION_UPLOADS_DIR
original_convert_fn = cd.convert_docx_to_markdown

with tempfile.TemporaryDirectory() as tmp:
    cd.VERIFICATION_UPLOADS_DIR = Path(tmp)

    try:
        print("--- save_upload: identical filenames from different documents must not collide ---")
        path1 = cd.save_upload(b"content of doc one", "thesis_draft.docx", document_id=9001)
        path2 = cd.save_upload(b"content of doc two", "thesis_draft.docx", document_id=9002)
        assert path1 != path2
        assert path1.read_bytes() == b"content of doc one"
        assert path2.read_bytes() == b"content of doc two"
        print("OK")

        print("\n--- ingest_verification_document: success path ---")
        cd.convert_docx_to_markdown = lambda path: "# A Heading\n\nSome converted markdown text."
        doc_id = cd.ingest_verification_document(b"fake docx bytes", "success.docx", user_id=None)
        with get_session() as session:
            doc = session.get(VerificationDocument, doc_id)
            assert doc.status == "extracting_claims"
            assert doc.markdown == "# A Heading\n\nSome converted markdown text."
            assert doc.error_message is None
            session.delete(doc)
        print("OK")

        print("\n--- ingest_verification_document: conversion failure is recorded, not raised ---")
        def raise_conversion_error(path):
            raise RuntimeError("simulated Docling failure")
        cd.convert_docx_to_markdown = raise_conversion_error
        doc_id2 = cd.ingest_verification_document(b"fake docx bytes", "failure.docx", user_id=None)
        with get_session() as session:
            doc = session.get(VerificationDocument, doc_id2)
            assert doc.status == "failed"
            assert "simulated Docling failure" in doc.error_message
            assert doc.markdown is None
            session.delete(doc)
        print("OK")

        print("\n--- ingest_verification_document: a save failure never even attempts conversion ---")
        conversion_was_called = {"value": False}

        def track_conversion(path):
            conversion_was_called["value"] = True
            return "should never get here"

        cd.convert_docx_to_markdown = track_conversion
        original_mkdir = Path.mkdir

        def failing_mkdir(self, *a, **kw):
            raise PermissionError("simulated disk failure")

        Path.mkdir = failing_mkdir
        try:
            doc_id3 = cd.ingest_verification_document(b"fake docx bytes", "save_failure.docx", user_id=None)
        finally:
            Path.mkdir = original_mkdir

        with get_session() as session:
            doc = session.get(VerificationDocument, doc_id3)
            assert doc.status == "failed"
            assert "Could not save" in doc.error_message
            session.delete(doc)
        assert conversion_was_called["value"] is False, "conversion must never run if saving the upload failed"
        print("OK")
    finally:
        cd.VERIFICATION_UPLOADS_DIR = original_uploads_dir
        cd.convert_docx_to_markdown = original_convert_fn

print("\nAll convert_docx assertions passed.")