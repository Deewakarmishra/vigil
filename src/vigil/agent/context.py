"""AlertContext — everything a single alert run needs, loaded once.

The agent reads only from this context + the session (never a live monitoring
engine), so every run is deterministic and replayable — which makes the backtest
(and the regulator-facing eval) trivial.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
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
    settings: Settings = field(default_factory=get_settings)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.alert.tenant_id

    @classmethod
    def load(cls, session: Session, alert_id: uuid.UUID) -> AlertContext:
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise ValueError(f"alert {alert_id} not found")
        customer = session.get(Customer, alert.customer_id) if alert.customer_id else None
        kyc = None
        baseline = None
        txns: list[Transaction] = []
        if customer is not None:
            kyc = session.scalars(select(KYCProfile).where(KYCProfile.customer_id == customer.id)).first()
            baseline = session.scalars(
                select(CustomerBaseline).where(CustomerBaseline.customer_id == customer.id)
            ).first()
            txns = list(
                session.scalars(
                    select(Transaction).where(Transaction.customer_id == customer.id).order_by(Transaction.occurred_on)
                )
            )
        return cls(
            session=session,
            alert=alert,
            customer=customer,
            kyc=kyc,
            baseline=baseline,
            transactions=txns,
            settings=get_settings(),
        )
