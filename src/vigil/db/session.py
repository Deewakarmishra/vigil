"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from vigil.config import Settings, get_settings

_ENGINE: Engine | None = None
SessionLocal: sessionmaker[Session] = sessionmaker(autocommit=False, autoflush=False, future=True)


def create_engine_from_settings(settings: Settings | None = None) -> Engine:
    s = settings or get_settings()
    return create_engine(
        s.database_url,
        pool_size=s.postgres_pool_size,
        max_overflow=s.postgres_pool_max_overflow,
        pool_pre_ping=True,
        future=True,
    )


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine_from_settings()
        SessionLocal.configure(bind=_ENGINE)
    return _ENGINE


def reset_engine() -> None:
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
        _ENGINE = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""

    get_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager wrapping a transactional unit of work."""

    get_engine()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
