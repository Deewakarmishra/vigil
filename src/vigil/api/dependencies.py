"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from vigil.db.session import get_session as _get_session


def get_session() -> Iterator[Session]:
    yield from _get_session()
