"""ConnectorAccount — per-tenant encrypted credentials for live connectors."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigil.db.base import Base
from vigil.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from vigil.security.encryption import decrypt_value, encrypt_value, mask_secret


class ConnectorAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connector_accounts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # shopify | helpdesk | carrier
    mode: Mapped[str] = mapped_column(String(16), default="mock", nullable=False)
    _secret: Mapped[str | None] = mapped_column("secret_encrypted", String, nullable=True)

    def set_credential(self, plaintext: str) -> None:
        self._secret = encrypt_value(plaintext)

    def get_credential(self) -> str | None:
        return decrypt_value(self._secret) if self._secret else None

    @property
    def masked(self) -> str:
        return mask_secret(self.get_credential() or "")
