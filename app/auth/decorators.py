"""
Auth decorators shared across admin-only API endpoints.
"""

from functools import wraps

from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_smorest import abort

from app.db.session import get_session
from app.models.user import User


def admin_required(fn):
    """Like @jwt_required(), but also re-checks is_admin against the
    database on every request, rather than trusting the is_admin claim
    baked into the JWT at login time. That claim can go stale: if an
    admin's access is revoked, their existing token would otherwise keep
    working as an admin token until it naturally expires. A DB lookup
    here means revocation takes effect on the very next request."""
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user_id = int(get_jwt_identity())
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None or not user.is_admin:
                abort(403, message="Admin access required")
        return fn(*args, **kwargs)
    return wrapper