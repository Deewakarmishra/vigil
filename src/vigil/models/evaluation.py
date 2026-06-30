"""Eval harness persistence: a run and its per-case scores."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigil.db.base import Base
from vigil.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EvalRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eval_runs"

    started_at: Mapped[_dt.datetime] = mapped_column(nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class EvalCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "eval_cases"

    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    predictions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ground_truth: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
