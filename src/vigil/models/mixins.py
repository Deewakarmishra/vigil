"""Reusable ORM mixins."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column


@declarative_mixin
class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


@declarative_mixin
class TimestampMixin:
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[_dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
