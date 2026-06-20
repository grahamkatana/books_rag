# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Pin uv to a specific version rather than :latest, for reproducible builds
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# Install dependencies first, in their own layer -- this is cached and
# skipped on rebuilds unless pyproject.toml/uv.lock actually change, so
# editing application code doesn't trigger a full dependency reinstall.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Now copy the application itself
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini server.py ./
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
