"""
Android app releases API. Run it against a throwaway SQLite file, never the real database:

    DATABASE_URL=sqlite:////tmp/releases_test.db uv run python tests/test_releases.py

It refuses to start on anything but SQLite, because it creates users and releases.
"""
import io, os, sys, zipfile
sys.path.insert(0, ".")

from app.config import DATABASE_URL
if not DATABASE_URL.startswith("sqlite"):
    sys.exit(f"REFUSING TO RUN: DATABASE_URL is not SQLite. Set DATABASE_URL=sqlite:////tmp/releases_test.db first.")

from app.api.factory import create_app
from app.api.v1 import releases as releases_module
from app.auth.security import hash_password
from app.db.session import engine, get_session
from app.models import Base
from app.models.app_release import AppRelease, AppReleaseFile
from app.models.user import User

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
with get_session() as session:
    session.add(User(email="admin@test.local", password_hash=hash_password("pw-admin"), is_admin=True))
    session.add(User(email="reader@test.local", password_hash=hash_password("pw-reader"), is_admin=False))

client = create_app().test_client()


def login(email, password):
    return {"Authorization": "Bearer " + client.post("/api/v1/auth/login", json={"email": email, "password": password}).get_json()["access_token"]}


def apk(extra=b""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("AndroidManifest.xml", b"<manifest/>")
        z.writestr("classes.dex", b"dex\n035" + extra)
    return buffer.getvalue()


def publish(headers, data, name="0.1.0", code="1", notes="First."):
    return client.post("/api/v1/releases/", headers=headers, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(data), "whatever-name.apk"), "version_name": name, "version_code": code, "notes": notes})


admin, reader = login("admin@test.local", "pw-admin"), login("reader@test.local", "pw-reader")

# --- nobody without a login sees anything; a reader cannot publish or delete ---
assert client.get("/api/v1/releases/").status_code == 401
assert publish(reader, apk()).status_code == 403
assert client.get("/api/v1/releases/", headers=reader).get_json() == {"releases": [], "total": 0}

# --- what is refused ---
assert publish(admin, b"not a zip").status_code == 422
not_an_apk = io.BytesIO()
with zipfile.ZipFile(not_an_apk, "w") as z:
    z.writestr("readme.txt", b"hello")
assert "not an APK" in publish(admin, not_an_apk.getvalue()).get_json()["message"]
assert publish(admin, apk(), name="../../etc").status_code == 422
assert publish(admin, apk(), code="0").status_code == 422
assert publish(admin, apk(), code="abc").status_code == 422
assert client.post("/api/v1/releases/", headers=admin, data={"version_name": "0.1.0", "version_code": "1"}).status_code == 400
releases_module.MAX_APK_BYTES, real_limit = 10, releases_module.MAX_APK_BYTES
assert publish(admin, apk()).status_code == 413
releases_module.MAX_APK_BYTES = real_limit

# --- publishing, and the rule that a version code is used once ---
first = publish(admin, apk())
assert first.status_code == 201, first.get_json()
assert first.get_json()["is_latest"] and first.get_json()["size_bytes"] == len(apk())
assert publish(admin, apk(b"x"), name="0.1.0-again").status_code == 409
second = publish(admin, apk(b"second"), name="0.2.0", code="2", notes="").get_json()
listed = client.get("/api/v1/releases/", headers=reader).get_json()
assert [(r["version_name"], r["is_latest"]) for r in listed["releases"]] == [("0.2.0", True), ("0.1.0", False)]
assert listed["releases"][0]["notes"] == "" and len(listed["releases"][0]["sha256"]) == 64

# --- downloading: only through a link, the link is for one release, and it expires ---
link = client.post(f"/api/v1/releases/{second['id']}/download-url", headers=reader).get_json()
assert link["filename"] == "book-rag-0.2.0.apk" and link["expires_in"] == 120
got = client.get(link["url"])  # no Authorization header, as a browser following a link
assert got.status_code == 200 and got.data == apk(b"second")
assert got.headers["Content-Disposition"] == 'attachment; filename="book-rag-0.2.0.apk"'
assert got.mimetype == "application/vnd.android.package-archive"
token = link["url"].split("t=")[1]
assert client.get(f"/api/v1/releases/{first.get_json()['id']}/file?t={token}").status_code == 401, "a link must not open another release"
assert client.get(f"/api/v1/releases/{second['id']}/file").status_code == 401
assert client.get(f"/api/v1/releases/{second['id']}/file?t={reader['Authorization'][7:]}").status_code == 401, "a login token must not open the file"
assert client.get("/api/v1/chats/", headers={"Authorization": f"Bearer {token}"}).status_code in (401, 422), "a download token must not work as a login"
releases_module.DOWNLOAD_LINK_SECONDS = -1
assert client.get(link["url"]).status_code == 401, "an expired link must be refused"
releases_module.DOWNLOAD_LINK_SECONDS = 120
assert client.post("/api/v1/releases/999/download-url", headers=reader).status_code == 404

# --- deleting takes the file with it ---
assert client.delete(f"/api/v1/releases/{second['id']}", headers=reader).status_code == 403
assert client.delete(f"/api/v1/releases/{second['id']}", headers=admin).get_json() == {"id": second["id"], "deleted": True}
assert client.delete(f"/api/v1/releases/{second['id']}", headers=admin).status_code == 404
with get_session() as session:
    assert session.query(AppRelease).count() == 1 and session.query(AppReleaseFile).count() == 1
assert client.get("/api/v1/releases/", headers=reader).get_json()["releases"][0]["is_latest"]

print("ALL RELEASE TESTS PASSED")
