#!/bin/sh
set -e

export PYTHONPATH=/app

echo "[api] running migrations..."
attempt=0
max_attempts="${MIGRATION_MAX_ATTEMPTS:-60}"
sleep_sec="${MIGRATION_RETRY_SLEEP_SEC:-1}"

set +e
while true; do
  alembic -c alembic.ini upgrade head
  code=$?
  if [ "$code" -eq 0 ]; then
    break
  fi
  attempt=$((attempt + 1))
  echo "[api] migrations failed (attempt $attempt/$max_attempts), retrying in ${sleep_sec}s..."
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "[api] migrations still failing, giving up."
    exit 1
  fi
  sleep "$sleep_sec"
done
set -e

echo "[api] starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000


