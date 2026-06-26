import sys
sys.path.insert(0, ".")

from unittest.mock import patch

from app.api.factory import create_app
from app.db.session import get_session
from app.models.user import User
from app.models.verification import VerificationDocument, ExtractedClaim, ClaimVerification
from app.auth.security import hash_password
from app.worker.celery_app import celery_app

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True
celery_app.conf.task_store_eager_result = True

EMAIL_A = "test_rerun_cc_endpoint_a@example.com"
EMAIL_B = "test_rerun_cc_endpoint_b@example.com"

with get_session() as session:
    for email in (EMAIL_A, EMAIL_B):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)

with get_session() as session:
    session.add(User(email=EMAIL_A, password_hash=hash_password("testpass123"), is_admin=False))
    session.add(User(email=EMAIL_B, password_hash=hash_password("testpass123"), is_admin=False))

app = create_app()
client = app.test_client()
token_a = client.post("/api/v1/auth/login", json={"email": EMAIL_A, "password": "testpass123"}).get_json()["access_token"]
token_b = client.post("/api/v1/auth/login", json={"email": EMAIL_B, "password": "testpass123"}).get_json()["access_token"]
h_a = {"Authorization": f"Bearer {token_a}"}
h_b = {"Authorization": f"Bearer {token_b}"}

with get_session() as session:
    user_a = session.query(User).filter_by(email=EMAIL_A).one()
    doc = VerificationDocument(filename="test_rerun_cc_doc.docx", status="done", markdown="content", user_id=user_a.id)
    session.add(doc)
    session.flush()
    c1 = ExtractedClaim(document_id=doc.id, order_index=0, text="Supported claim.")
    c2 = ExtractedClaim(document_id=doc.id, order_index=1, text="Contradicted claim.")
    session.add_all([c1, c2])
    session.flush()
    session.add(ClaimVerification(claim_id=c1.id, verdict="supported", confidence="high", explanation="x"))
    session.add(ClaimVerification(claim_id=c2.id, verdict="contradicted", confidence="high", explanation="x"))
    doc_id = doc.id
    supported_claim_id, contradicted_claim_id = c1.id, c2.id

    no_markdown_doc = VerificationDocument(filename="test_no_markdown.docx", status="failed", markdown=None, user_id=user_a.id)
    session.add(no_markdown_doc)
    session.flush()
    no_markdown_id = no_markdown_doc.id

print("--- GET detail includes document_context (null when not set) ---")
r = client.get(f"/api/v1/verification/{doc_id}", headers=h_a)
assert r.status_code == 200
assert "document_context" in r.get_json()
assert r.get_json()["document_context"] is None
print("OK")

print("\n--- no auth: 401 on both action endpoints ---")
assert client.post(f"/api/v1/verification/{doc_id}/rerun").status_code == 401
assert client.post(f"/api/v1/verification/{doc_id}/cross-check").status_code == 401
print("OK")

print("\n--- ownership: user B cannot rerun or cross-check user A's document ---")
assert client.post(f"/api/v1/verification/{doc_id}/rerun", headers=h_b).status_code == 404
assert client.post(f"/api/v1/verification/{doc_id}/cross-check", headers=h_b).status_code == 404
print("OK")

print("\n--- rerun on a document with no stored markdown: 400 ---")
assert client.post(f"/api/v1/verification/{no_markdown_id}/rerun", headers=h_a).status_code == 400
print("OK")

print("\n--- rerun: default from_extraction=True reaches the task ---")
with patch("app.worker.tasks.rerun_verification_task.delay") as mock_delay:
    mock_delay.return_value.id = "fake-task-id"
    r = client.post(f"/api/v1/verification/{doc_id}/rerun", headers=h_a)
    assert r.status_code == 202
    assert mock_delay.call_args[0] == (doc_id,)
    assert mock_delay.call_args[1]["from_extraction"] is True
print("OK")

print("\n--- rerun: ?from_extraction=false reaches the task correctly ---")
with patch("app.worker.tasks.rerun_verification_task.delay") as mock_delay:
    mock_delay.return_value.id = "fake-task-id"
    client.post(f"/api/v1/verification/{doc_id}/rerun?from_extraction=false", headers=h_a)
    assert mock_delay.call_args[1]["from_extraction"] is False
print("OK")

print("\n--- cross-check: returns the correct claim_ids, reachable for both reviewable claims ---")
with patch("app.worker.tasks.cross_check_document_task.delay") as mock_delay:
    mock_delay.return_value.id = "fake-task-id"
    r = client.post(f"/api/v1/verification/{doc_id}/cross-check", headers=h_a)
    assert r.status_code == 202
    body = r.get_json()
    assert set(body["claim_ids"]) == {supported_claim_id, contradicted_claim_id}
    assert body["document_id"] == doc_id
print("OK")

print("\n--- cross-check: verdicts filter narrows both the response and the task call ---")
with patch("app.worker.tasks.cross_check_document_task.delay") as mock_delay:
    mock_delay.return_value.id = "fake-task-id"
    r = client.post(f"/api/v1/verification/{doc_id}/cross-check?verdicts=contradicted", headers=h_a)
    assert r.get_json()["claim_ids"] == [contradicted_claim_id]
    assert mock_delay.call_args[1]["verdicts_to_check"] == ["contradicted"]
print("OK")

with get_session() as session:
    session.delete(session.get(VerificationDocument, doc_id))
    session.delete(session.get(VerificationDocument, no_markdown_id))
    for email in (EMAIL_A, EMAIL_B):
        user = session.query(User).filter_by(email=email).one_or_none()
        if user is not None:
            session.delete(user)

print("\nAll rerun/cross-check endpoint assertions passed.")