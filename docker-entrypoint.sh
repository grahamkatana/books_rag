#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Ensuring a default admin user exists..."
python -m app.auth.seed_admin

echo "Starting gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    server:app
