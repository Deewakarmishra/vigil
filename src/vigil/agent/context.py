"""AlertContext — everything a single alert run needs, loaded once.

The agent reads only from this context + the session (never a live monitoring
engine), so every run is deterministic and replayable — which makes the backtest
(and the regulator-facing eval) trivial. The transaction read is **window-bounded**
(``max_lookback_days``) so it stays cheap at scale; per-typology windows narrow it
further inside the detectors.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vigil.config import Settings, get_settings
from vigil.models.aml import Alert, Customer, CustomerBaseline, KYCProfile, Transaction


@dataclass
class AlertContext:
    session: Session
    alert: Alert
    customer: Customer | None
    kyc: KYCProfile | None
    baseline: CustomerBaseline | None
    transactions: list[Transaction] = field(default_factory=list)
    prior_alert_count: int = 0
    settings: Settings = field(default_factory=get_settings)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.alert.tenant_id

    @property
    def as_of(self) -> _dt.date:
        """The date detection windows are measured back from — the alert date."""

        received = self.alert.received_at
        return received.date() if received else _dt.date.today()

    @classmethod
    def load(cls, session: Session, alert_id: uuid.UUID) -> AlertContext:
        settings = get_settings()
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"alert {alert_id} not found")
        customer = session.get(Customer, alert.customer_id) if alert.customer_id else None
        kyc = None
        baseline = None
        txns: list[Transaction] = []
        prior_alert_count = 0
        if customer is not None:
            kyc = session.scalars(select(KYCProfile).where(KYCProfile.customer_id == customer.id)).first()
            baseline = session.scalars(
                select(CustomerBaseline).where(CustomerBaseline.customer_id == customer.id)
            ).first()
            # Bounded read: only the recent lookback, ordered oldest→newest.
            as_of = alert.received_at.date() if alert.received_at else _dt.date.today()
            cutoff = as_of - _dt.timedelta(days=settings.max_lookback_days)
            txns = list(
                session.scalars(
                    select(Transaction)
                    .where(Transaction.customer_id == customer.id, Transaction.occurred_on >= cutoff)
                    .order_by(Transaction.occurred_on)
                )
            )
            # Real prior-alert signal (was hardcoded 0): other alerts for this customer.
            prior_alert_count = (
                session.scalar(
                    select(func.count())
                    .select_from(Alert)
                    .where(Alert.customer_id == customer.id, Alert.id != alert.id)
                )
                or 0
            )
        return cls(
            session=session,
            alert=alert,
            customer=customer,
            kyc=kyc,
            baseline=baseline,
            transactions=txns,
            prior_alert_count=int(prior_alert_count),
            settings=settings,
        )
