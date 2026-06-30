"""AML data model: customers, KYC, transactions, alerts, hypotheses, dispositions, SAR drafts.

The flow: a monitoring **alert** fires on a **customer**; the agent enriches it with
**KYC**, the **transaction** lookback, **counterparties**, and the customer's
**baseline**; forms **typology hypotheses**; binds each to the **transactions** that
prove it via the **alert_evidence** citation join; and records a **disposition**
(with its full reasoning trace) — escalations carry a **SAR draft**. The officer
disposes and files; the agent never does.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from vigil.db.base import Base
from vigil.models.enums import AlertStatus, Disposition, RiskRating, SARStatus
from vigil.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), default="individual", nullable=False)
    risk_rating: Mapped[str] = mapped_column(String(8), default=RiskRating.LOW.value, nullable=False)


class KYCProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "kyc_profiles"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_activity: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # expected volume/velocity
    pep: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    adverse_media: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarded_at: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)


class Counterparty(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "counterparties"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    relationship: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk: Mapped[str] = mapped_column(String(8), default=RiskRating.LOW.value, nullable=False)


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_txn_id: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # credit | debit
    channel: Mapped[str | None] = mapped_column(String(24), nullable=True)  # cash | wire | ach | card
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("counterparties.id", ondelete="SET NULL"), nullable=True
    )
    counterparty_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_on: Mapped[_dt.date] = mapped_column(Date, nullable=False, index=True)


class CustomerBaseline(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A per-customer behavioral baseline — expected-vs-observed is how AI cuts FPs."""

    __tablename__ = "customer_baselines"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    window_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    expected_max_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)  # per-window ceiling
    expected_channels: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "alerts"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_alert_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    spec_key: Mapped[str | None] = mapped_column(String(64), nullable=True)  # links seed → eval ground truth
    rule_id: Mapped[str] = mapped_column(String(48), nullable=False)
    alert_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    received_at: Mapped[_dt.datetime] = mapped_column(nullable=False)
    age_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # backlog visibility
    status: Mapped[str] = mapped_column(String(16), default=AlertStatus.NEW.value, nullable=False)
    disposition: Mapped[str] = mapped_column(String(16), default=Disposition.NEED_INFO.value, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scope_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # AlertScope snapshot


class TypologyHypothesis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "typology_hypotheses"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    typology: Mapped[str] = mapped_column(String(32), nullable=False)
    likelihood: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)


class AlertEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The citation join: a typology claim bound to the transaction that proves it."""

    __tablename__ = "alert_evidence"

    typology_hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("typology_hypotheses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False
    )
    locator: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "Txn TXN-0007"
    quote: Mapped[str] = mapped_column(Text, default="", nullable=False)


class DispositionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recorded disposition + its full reasoning trace (the exam artifact)."""

    __tablename__ = "dispositions"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # clear | escalate | need_info
    rationale_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decided_by: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)  # agent | officer
    reasoning_trace: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class SARDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A regulator-readable SAR draft. Never auto-filed — an officer files."""

    __tablename__ = "sar_drafts"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    narrative_md: Mapped[str] = mapped_column(Text, default="", nullable=False)
    five_w: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # who/what/when/where/why
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    period_start: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[_dt.date | None] = mapped_column(Date, nullable=True)
    evidence_index: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=SARStatus.DRAFT.value, nullable=False)
    filed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
