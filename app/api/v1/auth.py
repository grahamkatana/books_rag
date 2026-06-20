from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from app.db.session import get_session
from app.models.user import User
from app.auth.security import verify_password
from app.api.v1.auth_schemas import LoginRequestSchema, LoginResponseSchema, MeResponseSchema

blp = Blueprint(
    "auth", __name__,
    url_prefix="/api/v1/auth",
    description="Login and current-user info",
)


@blp.route("/login", methods=["POST"])
class Login(MethodView):
    @blp.arguments(LoginRequestSchema)
    @blp.response(200, LoginResponseSchema)
    def post(self, args):
        """Exchange an email + password for a JWT access token."""
        with get_session() as session:
            user = session.query(User).filter_by(email=args["email"]).one_or_none()
            if user is None or not verify_password(args["password"], user.password_hash):
                abort(401, message="Invalid email or password")

            token = create_access_token(
                identity=str(user.id),
                additional_claims={"email": user.email, "is_admin": user.is_admin},
            )
            return {"access_token": token, "email": user.email, "is_admin": user.is_admin}


@blp.route("/me")
class Me(MethodView):
    @jwt_required()
    @blp.response(200, MeResponseSchema)
    def get(self):
        """Return the currently authenticated user, based on the bearer token."""
        with get_session() as session:
            user = session.get(User, int(get_jwt_identity()))
            if user is None:
                abort(401, message="User no longer exists")
            return {"id": user.id, "email": user.email, "is_admin": user.is_admin}
