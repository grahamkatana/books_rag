"""
Flask application factory. Versioning lives in each blueprint's
url_prefix (/api/v1/...) -- adding a v2 later means a new app/api/v2/
package and one more api.register_blueprint() call here, without
touching any v1 code.
"""

import time

from flask import Flask, jsonify, request, g
from flask_cors import CORS
from flask_smorest import Api
from flask_jwt_extended import JWTManager

from app.config import SECRET_KEY, JWT_SECRET_KEY
from app.logging_config import setup_logging, get_logger

logger = get_logger(__name__)


def create_app() -> Flask:
    setup_logging()

    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY

    app.config["API_TITLE"] = "Book RAG API"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    app.config["OPENAPI_URL_PREFIX"] = "/"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "/swagger-ui"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"
    app.config["OPENAPI_JSON_PATH"] = "api-spec.json"

    # Permissive by default for local development -- a browser-based
    # frontend on a different port can call this without a CORS error.
    # Tighten this (specific origins) before this is reachable by anyone
    # other than you.
    CORS(app)

    JWTManager(app)

    api = Api(app)

    from app.api.v1.books import blp as books_blp
    from app.api.v1.papers import blp as papers_blp
    from app.api.v1.chats import blp as chats_blp
    from app.api.v1.verification import blp as verification_blp
    from app.api.v1.ask import blp as ask_blp
    from app.api.v1.auth import blp as auth_blp
    from app.api.v1.admin_users import blp as admin_users_blp
    from app.api.v1.admin_books import blp as admin_books_blp
    from app.api.v1.admin_papers import blp as admin_papers_blp
    from app.api.v1.admin_chats import blp as admin_chats_blp
    from app.api.v1.admin_jobs import blp as admin_jobs_blp
    from app.api.v1.admin_ingest import blp as admin_ingest_blp
    from app.api.v1.admin_corpus_context import blp as admin_corpus_context_blp

    api.register_blueprint(books_blp)
    api.register_blueprint(papers_blp)
    api.register_blueprint(chats_blp)
    api.register_blueprint(verification_blp)
    api.register_blueprint(ask_blp)
    api.register_blueprint(auth_blp)
    api.register_blueprint(admin_users_blp)
    api.register_blueprint(admin_books_blp)
    api.register_blueprint(admin_papers_blp)
    api.register_blueprint(admin_chats_blp)
    api.register_blueprint(admin_jobs_blp)
    api.register_blueprint(admin_ingest_blp)
    api.register_blueprint(admin_corpus_context_blp)

    from app.admin.views import register_admin
    register_admin(app)

    @app.before_request
    def _log_request_start():
        g._start_time = time.time()

    @app.after_request
    def _log_request_end(response):
        duration_ms = (time.time() - g.get("_start_time", time.time())) * 1000
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response

    @app.route("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    return app