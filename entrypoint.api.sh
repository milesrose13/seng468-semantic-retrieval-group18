#!/bin/sh
set -e

echo "Running database migrations..."
cd /app && alembic upgrade head

echo "Starting API server..."
cd /app/backend && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
