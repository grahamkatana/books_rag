"""
Admin-only CRUD endpoints for managing users via the API, as an
alternative to the /admin server-rendered panel. Every endpoint here
requires admin_required (a real DB lookup, not just a JWT claim -- see
app/auth/decorators.py).

Endpoints:
    GET    /api/v1/admin/users/        list every user
    GET    /api/v1/admin/users/<id>    get one user
    POST   /api/v1/admin/users/        register a new user
    PUT    /api/v1/admin/users/<id>    update a user (any field optional)
    DELETE /api/v1/admin/users/<id>    delete a user

Two safety rules enforced here, not just in the UI: you can never delete
or demote the last remaining admin (that's a permanent self-lockout with
no recovery path other than direct DB access), and creating a user with
an email that already exists comes back as a clean 409, not a raw DB
constraint crash.
"""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema, fields, validate

from app.db.session import get_session
from app.models.user import User
from app.auth.security import hash_password
from app.auth.decorators import admin_required

blp = Blueprint(
    "admin_users", __name__,
    url_prefix="/api/v1/admin/users",
    description="Admin-only user management (list/create/update/delete)",
)


# --- schemas -----------------------------------------------------------

class AdminUserSchema(Schema):
    id = fields.Int()
    email = fields.Email()
    is_admin = fields.Bool()
    created_at = fields.DateTime()


class AdminUserCreateSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))
    is_admin = fields.Bool(load_default=False)


class AdminUserUpdateSchema(Schema):
    # Every field optional -- this is a partial update (PATCH semantics
    # even though the route is PUT, matching how seed_admin/create_user's
    # --update flag works elsewhere in this project).
    email = fields.Email(required=False)
    password = fields.Str(required=False, validate=validate.Length(min=8))
    is_admin = fields.Bool(required=False)


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "is_admin": user.is_admin,
        "created_at": user.created_at,
    }


def count_other_admins(session, exclude_user_id: int) -> int:
    return (
        session.query(User)
        .filter(User.is_admin.is_(True), User.id != exclude_user_id)
        .count()
    )


# --- endpoints -----------------------------------------------------------

@blp.route("/")
class AdminUserList(MethodView):
    @admin_required
    @blp.response(200, AdminUserSchema(many=True))
    def get(self):
        """List every user."""
        with get_session() as session:
            users = session.query(User).order_by(User.id).all()
            return [user_to_dict(u) for u in users]

    @admin_required
    @blp.arguments(AdminUserCreateSchema)
    @blp.response(201, AdminUserSchema)
    def post(self, args):
        """Register a new user."""
        with get_session() as session:
            if session.query(User).filter_by(email=args["email"]).one_or_none() is not None:
                abort(409, message=f"A user with email {args['email']!r} already exists")

            user = User(
                email=args["email"],
                password_hash=hash_password(args["password"]),
                is_admin=args["is_admin"],
            )
            session.add(user)
            session.flush()
            return user_to_dict(user)


@blp.route("/<int:user_id>")
class AdminUserDetail(MethodView):
    @admin_required
    @blp.response(200, AdminUserSchema)
    def get(self, user_id):
        """Get one user by id."""
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                abort(404, message="User not found")
            return user_to_dict(user)

    @admin_required
    @blp.arguments(AdminUserUpdateSchema)
    @blp.response(200, AdminUserSchema)
    def put(self, args, user_id):
        """Update a user. Any field can be omitted to leave it unchanged."""
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                abort(404, message="User not found")

            # Refuse to demote the last admin -- that's a permanent
            # lockout with no recovery path short of editing the
            # database directly.
            if "is_admin" in args and args["is_admin"] is False and user.is_admin:
                if count_other_admins(session, exclude_user_id=user.id) == 0:
                    abort(409, message="Cannot remove admin from the last remaining admin")

            if "email" in args:
                conflict = session.query(User).filter(
                    User.email == args["email"], User.id != user_id
                ).one_or_none()
                if conflict is not None:
                    abort(409, message=f"A user with email {args['email']!r} already exists")
                user.email = args["email"]

            if "password" in args:
                user.password_hash = hash_password(args["password"])

            if "is_admin" in args:
                user.is_admin = args["is_admin"]

            session.add(user)
            session.flush()
            return user_to_dict(user)

    @admin_required
    def delete(self, user_id):
        """Delete a user."""
        requester_id = int(get_jwt_identity())

        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                abort(404, message="User not found")

            if user.is_admin and count_other_admins(session, exclude_user_id=user.id) == 0:
                abort(409, message="Cannot delete the last remaining admin")

            if user.id == requester_id:
                abort(409, message="Cannot delete your own account while logged in as it -- "
                                    "use a different admin account")

            session.delete(user)
        return "", 204