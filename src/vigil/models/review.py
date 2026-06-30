"""HITL queue: officer-disposition tasks for escalations and RFIs."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigil.db.base import Base
from vigil.models.enums import ReviewStatus
from vigil.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ReviewTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_tasks"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(24), default="escalation", nullable=False)  # escalation | rfi | low_conf
    status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.OPEN.value, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    closed_at: Mapped[_dt.datetime | None] = mapped_column(nullable=True)


class ReviewAction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_actions"

    review_task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    after: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
