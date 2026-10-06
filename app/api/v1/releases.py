"""
Android app releases: every published version of the app is kept and can
be downloaded again.

    GET    /api/v1/releases/                    all versions, newest first
    POST   /api/v1/releases/                    publish a version (admin; multipart)
    POST   /api/v1/releases/<id>/download-url   a link to the file, valid for 2 minutes
    GET    /api/v1/releases/<id>/file?t=...     the APK, as an attachment
    DELETE /api/v1/releases/<id>                delete a version (admin)

Why a separate download link: a phone's browser downloads a file by
following a plain link, and a plain link cannot carry the Authorization
header. So a logged-in user asks for a short-lived link and the browser
follows that. The link's token is signed with its own salt and is not a
JWT, so it opens nothing else in the API, and a login token does not
open the file.
"""

import hashlib
import io
import re
import zipfile

from flask import Response, request
from flask.views import MethodView
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_smorest import Blueprint, abort
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.auth.decorators import admin_required
from app.config import SECRET_KEY
from app.db.session import get_session
from app.models.app_release import AppRelease, AppReleaseFile

MAX_APK_BYTES = 50 * 1024 * 1024  # frontend/nginx.conf accepts uploads up to the same size
DOWNLOAD_LINK_SECONDS = 120
_VERSION_NAME = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,39}$")
_download_signer = URLSafeTimedSerializer(SECRET_KEY, salt="app-release-download")

blp = Blueprint(
    "releases", __name__,
    url_prefix="/api/v1/releases",
    description="Published versions of the Android app",
)


def validate_apk(data: bytes) -> None:
    """An APK is a zip holding AndroidManifest.xml and compiled code; anything else is refused.

    This does not prove the app is safe or properly signed -- only admins can
    publish, and the sha256 is shown so the file can be checked -- it stops a
    wrong file being published by mistake.
    """
    if not data:
        raise ValueError("The file is empty.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as apk:
            names = set(apk.namelist())
    except zipfile.BadZipFile:
        raise ValueError("This is not an APK: it is not a valid zip archive.")
    if "AndroidManifest.xml" not in names or not any(n.endswith(".dex") for n in names):
        raise ValueError("This is not an APK: it has no AndroidManifest.xml or compiled code.")


def _filename(release: AppRelease) -> str:
    # Built from the version, never from whatever name the uploaded file had.
    return f"book-rag-{release.version_name}.apk"


def _to_dict(release: AppRelease, latest_code: int | None) -> dict:
    return {
        "id": release.id,
        "version_name": release.version_name,
        "version_code": release.version_code,
        "size_bytes": release.size_bytes,
        "sha256": release.sha256,
        "notes": release.notes or "",
        "created_at": release.created_at.isoformat() if release.created_at else None,
        "is_latest": release.version_code == latest_code,
    }


@blp.route("/")
class ReleaseList(MethodView):
    @jwt_required()
    def get(self):
        """Every published version of the Android app, newest first."""
        with get_session() as session:
            releases = session.query(AppRelease).order_by(AppRelease.version_code.desc()).all()
            latest = releases[0].version_code if releases else None
            return {"releases": [_to_dict(r, latest) for r in releases], "total": len(releases)}

    @admin_required
    def post(self):
        """Publish a new version (admin). Multipart: file, version_name, version_code, notes. Older versions are kept."""
        version_name = (request.form.get("version_name") or "").strip()
        if not _VERSION_NAME.match(version_name):
            abort(422, message="Version name may use letters, digits and . _ + - only (up to 40 characters), e.g. 0.1.0")
        try:
            version_code = int(request.form.get("version_code") or "")
        except ValueError:
            abort(422, message="Version code must be a whole number.")
        # Android itself refuses version codes above 2,100,000,000.
        if not 1 <= version_code <= 2_100_000_000:
            abort(422, message="Version code must be between 1 and 2,100,000,000.")

        file = request.files.get("file")
        if not file:
            abort(400, message="No file provided. Send it as multipart/form-data under the 'file' field.")
        data = file.read(MAX_APK_BYTES + 1)
        if len(data) > MAX_APK_BYTES:
            abort(413, message=f"The file is larger than {MAX_APK_BYTES // (1024 * 1024)} MB.")
        try:
            validate_apk(data)
        except ValueError as e:
            abort(422, message=str(e))

        with get_session() as session:
            if session.query(AppRelease.id).filter_by(version_code=version_code).first() is not None:
                abort(409, message=f"Version code {version_code} is already published. Use a higher number for a new version.")
            release = AppRelease(
                version_name=version_name,
                version_code=version_code,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                notes=(request.form.get("notes") or "").strip() or None,
                uploaded_by=int(get_jwt_identity()),
            )
            session.add(release)
            session.flush()
            session.add(AppReleaseFile(release_id=release.id, data=data))
            session.flush()
            latest = session.query(AppRelease.version_code).order_by(AppRelease.version_code.desc()).first()[0]
            return _to_dict(release, latest), 201


@blp.route("/<int:release_id>/download-url")
class ReleaseDownloadUrl(MethodView):
    @jwt_required()
    def post(self, release_id):
        """A short-lived link to the file. Open it in the phone's browser to download."""
        with get_session() as session:
            release = session.get(AppRelease, release_id)
            if release is None:
                abort(404, message="Release not found")
            return {
                "url": f"/api/v1/releases/{release_id}/file?t={_download_signer.dumps(release_id)}",
                "expires_in": DOWNLOAD_LINK_SECONDS,
                "filename": _filename(release),
            }


@blp.route("/<int:release_id>/file")
class ReleaseFile(MethodView):
    def get(self, release_id):
        """The APK. Authorised by the token from POST /<id>/download-url, not by a login header."""
        try:
            allowed = _download_signer.loads(request.args.get("t", ""), max_age=DOWNLOAD_LINK_SECONDS) == release_id
        except BadSignature:  # also covers an expired link
            allowed = False
        if not allowed:
            abort(401, message="This download link is invalid or has expired. Request a new one.")
        with get_session() as session:
            release = session.get(AppRelease, release_id)
            stored = session.get(AppReleaseFile, release_id)
            if release is None or stored is None:
                abort(404, message="Release not found")
            return Response(
                stored.data,
                mimetype="application/vnd.android.package-archive",
                headers={
                    "Content-Disposition": f'attachment; filename="{_filename(release)}"',
                    "X-Content-Type-Options": "nosniff",
                    "Cache-Control": "private, no-store",
                },
            )


@blp.route("/<int:release_id>")
class ReleaseDetail(MethodView):
    @admin_required
    def delete(self, release_id):
        """Delete a version (admin). Phones that already have it keep working."""
        with get_session() as session:
            release = session.get(AppRelease, release_id)
            if release is None:
                abort(404, message="Release not found")
            # Deleted explicitly rather than relying on ON DELETE CASCADE, so SQLite and Postgres behave the same.
            session.query(AppReleaseFile).filter_by(release_id=release_id).delete()
            session.delete(release)
        return {"id": release_id, "deleted": True}
