"""
Shared file-upload handling for the book/paper upload endpoints --
validation, collision checking, and saving. Common to both
admin_books.py and admin_papers.py's /upload routes, the same reason
delete_common.py exists for the delete endpoints: one real
implementation rather than two copies that can drift apart.
"""

from pathlib import Path

from flask_smorest import abort
from werkzeug.datastructures import FileStorage


def save_uploaded_pdf(file: FileStorage, target_dir: Path) -> Path:
    """Validates and saves an uploaded PDF, aborting with a clear HTTP
    error (400/409) on anything wrong, rather than returning an error
    for the caller to check -- consistent with how the rest of this API
    already uses flask_smorest's abort() for validation failures.

    Rejects, rather than silently overwriting or auto-renaming, a
    filename that already exists in target_dir: an overwrite could
    leave an already-ingested source_key pointing at content that no
    longer matches what was originally embedded, which is worse than
    just asking the uploader to rename the file or delete the existing
    one first."""
    if not file or not file.filename:
        abort(400, message="No file provided. Send it as multipart/form-data under the 'file' field.")

    if not file.filename.lower().endswith(".pdf"):
        abort(400, message="Only .pdf files are accepted.")

    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / file.filename

    if destination.exists():
        abort(409, message=f"A file named '{file.filename}' already exists. "
                            f"Rename the file, or delete the existing one first.")

    file.save(destination)
    return destination