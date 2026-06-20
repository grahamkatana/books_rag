"""
Production server entrypoint.

Uses waitress instead of Flask's built-in dev server (not safe for
production: single-threaded, no real concurrency, verbose debug output)
and instead of gunicorn (doesn't run on Windows at all -- it relies on
os.fork, which Windows doesn't have). waitress is pure Python and runs
identically on Windows, Linux, and macOS.

Usage:
    uv run python server.py
    uv run python server.py --port 8080 --host 127.0.0.1
"""

import argparse

from waitress import serve

from app.api.factory import create_app

app = create_app()


def main():
    parser = argparse.ArgumentParser(description="Run the Book RAG API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--threads", type=int, default=4,
                         help="Worker threads -- raise this if /ask feels slow under concurrent requests")
    args = parser.parse_args()

    print(f"Serving on http://{args.host}:{args.port}  (Swagger UI: http://{args.host}:{args.port}/swagger-ui)")
    serve(app, host=args.host, port=args.port, threads=args.threads)


if __name__ == "__main__":
    main()
