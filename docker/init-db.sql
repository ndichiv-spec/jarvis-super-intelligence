# Placeholder for database initialization scripts.
# This file is mounted at /docker-entrypoint-initdb.d/init.sql in the
# postgres container so it runs automatically on first start.

CREATE SCHEMA IF NOT EXISTS jarvis;
SET search_path TO jarvis;

-- Add any custom tables or extensions here. The application's SQLAlchemy
-- models will create their own tables via alembic/migrations on first run.
