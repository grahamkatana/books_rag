#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Ensuring a default admin user exists..."
python -m app.auth.seed_admin

# prometheus-client multiprocess mode: each gunicorn worker writes its own
# *.db file here and /metrics merges them, so request counts/latency aren't
# halved by scrape round-robin across the 2 workers.
mkdir -p "${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-multiproc}"

echo "Starting gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --worker-class gthread \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    server:app
