import sys
sys.path.insert(0, ".")

from unittest.mock import patch

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password
from app.worker.celery_app import celery_app
import app.cli as cli

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

ADMIN_EMAIL = "test_admin_ingest_admin@example.com"
PLAIN_EMAIL = "test_admin_ingest_plain@example.com"

with get_session() as session:
    for email in (ADMIN_EMAIL, PLAIN_EMAIL):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)

with get_session() as session:
    session.add(User(email=ADMIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=True))
    session.add(User(email=PLAIN_EMAIL, password_hash=hash_password("testpass123"), is_admin=False))

app = create_app()
client = app.test_client()
admin_token = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
plain_token = client.post("/api/v1/auth/login", json={"email": PLAIN_EMAIL, "password": "testpass123"}).get_json()["access_token"]
admin_h = {"Authorization": f"Bearer {admin_token}"}
plain_h = {"Authorization": f"Bearer {plain_token}"}

with patch.object(cli, "cmd_pipeline") as mock_pipeline, patch.object(cli, "cmd_pipeline_papers") as mock_pipeline_papers:
    print("--- non-admin: 403 ---")
    assert client.post("/api/v1/admin/ingest/", headers=plain_h).status_code == 403
    print("OK")

    print("\n--- admin, default force=False: 202, both task_ids present, both pipelines actually ran ---")
    r = client.post("/api/v1/admin/ingest/", headers=admin_h)
    assert r.status_code == 202
    body = r.get_json()
    assert "books_task_id" in body and "papers_task_id" in body
    assert body["books_task_id"] != body["papers_task_id"]
    assert mock_pipeline.called and mock_pipeline_papers.called
    assert mock_pipeline.call_args[0][0].force is False
    assert mock_pipeline_papers.call_args[0][0].force is False
    print("OK")

    print("\n--- admin, force=true: both pipelines receive force=True ---")
    mock_pipeline.reset_mock()
    mock_pipeline_papers.reset_mock()
    r = client.post("/api/v1/admin/ingest/?force=true", headers=admin_h)
    assert r.status_code == 202
    assert mock_pipeline.call_args[0][0].force is True
    assert mock_pipeline_papers.call_args[0][0].force is True
    print("OK")

with get_session() as session:
    for email in (ADMIN_EMAIL, PLAIN_EMAIL):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)

print("\nAll admin_ingest assertions passed.")