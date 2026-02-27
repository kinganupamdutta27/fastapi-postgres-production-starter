#!/bin/sh
set -e

# Run Alembic migrations (connect directly to PostgreSQL, bypassing PgBouncer for DDL)
echo "Running database migrations..."
alembic -x sqlalchemy.url=postgresql://${DATABASE_USER}:${DATABASE_PASSWORD}@postgres:5432/${DATABASE_NAME} upgrade head

echo "Starting application..."
exec "$@"
