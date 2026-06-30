"""Dev DB bootstrap: create the database if missing, then create all tables.

Production uses Alembic; this keeps the demo a single command on a clean machine.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

import vigil.models  # noqa: F401 — registers all tables on Base.metadata
from vigil.config import get_settings
from vigil.db.base import Base
from vigil.db.session import get_engine, reset_engine


def ensure_database() -> bool:
    """Create the configured Postgres database if it does not exist."""

    s = get_settings()
    created = False
    admin = create_engine(s.server_url, isolation_level="AUTOCOMMIT", future=True)
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": s.postgres_db}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{s.postgres_db}"'))
                created = True
    finally:
        admin.dispose()
    reset_engine()
    return created


def create_all() -> None:
    Base.metadata.create_all(get_engine())
