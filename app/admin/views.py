"""
Minimal Flask-Admin panel, mounted at /admin. Gated to users with
is_admin=True via Flask-Login session auth -- deliberately separate from
the JWT auth the React frontend uses, since this is a server-rendered
panel with its own login page, not an API consumer.
"""

from flask import redirect, url_for, request, render_template_string, Blueprint
from flask_admin import Admin, AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from wtforms import PasswordField
from wtforms.validators import Optional as OptionalValidator

from app.db.session import AdminScopedSession
from app.models.user import User
from app.models.book import Book
from app.models.chat import Chat
from app.auth.security import hash_password, verify_password

admin_auth_bp = Blueprint("admin_auth", __name__)

LOGIN_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>Book RAG Admin</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 320px; margin: 100px auto; color: #1f2937; }
    h2 { margin-bottom: 4px; }
    input { width: 100%; padding: 8px; margin: 6px 0; box-sizing: border-box;
            border: 1px solid #d1d5db; border-radius: 6px; }
    button { width: 100%; padding: 9px; background: #2563eb; color: white; border: none;
             border-radius: 6px; font-weight: 500; cursor: pointer; }
    button:hover { background: #1d4ed8; }
    .error { color: #dc2626; font-size: 14px; }
  </style>
</head>
<body>
  <h2>Book RAG Admin</h2>
  {% if error %}<p class="error">{{ error }}</p>{% endif %}
  <form method="post">
    <input type="email" name="email" placeholder="Email" required autofocus>
    <input type="password" name="password" placeholder="Password" required>
    <button type="submit">Log in</button>
  </form>
</body>
</html>
"""


@admin_auth_bp.route("/admin/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        session = AdminScopedSession()
        user = session.query(User).filter_by(email=request.form.get("email", "")).one_or_none()
        if user and user.is_admin and verify_password(request.form.get("password", ""), user.password_hash):
            login_user(user)
            return redirect(request.args.get("next") or url_for("admin.index"))
        error = "Invalid email/password, or this account isn't an admin."
    return render_template_string(LOGIN_TEMPLATE, error=error)


@admin_auth_bp.route("/admin/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin_auth.login"))


def init_login_manager(app):
    login_manager = LoginManager()
    login_manager.login_view = "admin_auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return AdminScopedSession().get(User, int(user_id))

    return login_manager


class AdminAccessMixin:
    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, "is_admin", False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin_auth.login", next=request.url))


class SecureAdminIndexView(AdminAccessMixin, AdminIndexView):
    @expose("/")
    def index(self):
        if not self.is_accessible():
            return self.inaccessible_callback("index")
        return super().index()


class UserAdminView(AdminAccessMixin, ModelView):
    column_list = ["id", "email", "is_admin", "created_at"]
    column_searchable_list = ["email"]
    form_columns = ["email", "is_admin"]
    form_extra_fields = {
        "password": PasswordField(
            "Password (leave blank to keep unchanged when editing)",
            validators=[OptionalValidator()],
        )
    }

    def on_model_change(self, form, model, is_created):
        if form.password.data:
            model.password_hash = hash_password(form.password.data)
        elif is_created:
            raise ValueError("Password is required when creating a new user")


class BookAdminView(AdminAccessMixin, ModelView):
    # This is the manual-correction path now that book_overrides.json is
    # gone entirely: editing a book's bibliography here writes straight
    # to the database, same as lookup-bibliography does, no JSON file
    # involved anywhere in the system.
    column_list = ["id", "title", "authors", "is_editor", "year", "publisher",
                    "edition", "page_mode", "work_key", "is_preferred_edition", "edition_pinned",
                    "bibliography_verified", "bibliography_source", "lookup_confidence"]
    column_searchable_list = ["title", "authors", "source_key"]
    form_columns = ["title", "authors", "is_editor", "year", "publisher", "edition",
                     "page_mode", "work_key", "is_preferred_edition", "edition_pinned",
                     "bibliography_verified"]

    def on_model_change(self, form, model, is_created):
        # A manual admin edit is, definitionally, a human having looked
        # at it -- mark it verified and tag its source so lookup-bibliography
        # never overwrites this correction later.
        model.bibliography_verified = True
        model.bibliography_source = "manual"


class ChatAdminView(AdminAccessMixin, ModelView):
    column_list = ["id", "title", "user_id", "created_at"]
    can_create = False
    can_edit = False


def register_admin(app):
    init_login_manager(app)
    app.register_blueprint(admin_auth_bp)

    @app.teardown_appcontext
    def remove_admin_session(exception=None):
        AdminScopedSession.remove()

    admin = Admin(app, name="Book RAG Admin", index_view=SecureAdminIndexView(url="/admin"), theme=Bootstrap4Theme())
    admin.add_view(UserAdminView(User, AdminScopedSession, name="Users"))
    admin.add_view(BookAdminView(Book, AdminScopedSession, name="Books"))
    admin.add_view(ChatAdminView(Chat, AdminScopedSession, name="Chats"))
