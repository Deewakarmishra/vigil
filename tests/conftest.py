"""Shared fixtures. Integration tests use a throwaway local Postgres database."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session")
def _pg_available() -> bool:
    return True


@pytest.fixture()
def seeded_session():
    """Yield a session against a freshly-created throwaway DB, seeded with demo data.

    Skips if Postgres is unreachable.
    """

    import sqlalchemy
    from sqlalchemy import text

    os.environ.setdefault("POSTGRES_DB", "vigil_test")
    from vigil.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    # Create the test DB.
    try:
        admin = sqlalchemy.create_engine(settings.server_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            exists = c.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": settings.postgres_db}).scalar()
            if not exists:
                c.execute(text(f'CREATE DATABASE "{settings.postgres_db}"'))
        admin.dispose()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Postgres unavailable: {e}")

    import vigil.models  # noqa
    from vigil.db.base import Base
    from vigil.db.bootstrap import create_all
    from vigil.db.session import get_engine, reset_engine, session_scope
    from vigil.models.tenant import Tenant  # noqa

    reset_engine()
    # Reset to a clean schema each run so tests are deterministic.
    Base.metadata.drop_all(get_engine())
    create_all()
    from vigil.synthetic.generator import seed_demo

    with session_scope() as s:
        seed_demo(s, settings)
    with session_scope() as s:
        yield s
