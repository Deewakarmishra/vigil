"""Routing policy DSL: a definition with content-hashed versions."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigil.db.base import Base
from vigil.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PolicyDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_definitions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class PolicyVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_versions"

    policy_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("policy_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    yaml_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rules: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
