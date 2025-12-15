#!/bin/sh
set -e

export PYTHONPATH=/app

echo "[api] running migrations..."
alembic -c alembic.ini upgrade head

echo "[api] starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000


