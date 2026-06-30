"""Deterministic synthetic bank: customers, KYC, baselines, transactions, and
monitoring alerts with planted typologies + planted false positives.

``CASE_SPECS`` is the single source of truth for both the seed and the eval ground
truth, so the demo and the backtest never drift apart. Transaction dates are
relative to *now* so the lookback is reproducible. Typologies are shaped after
published FATF/FinCEN patterns (structuring / layering / mule); false positives
are legitimate flows that sit within the customer's own baseline.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from vigil.config import Settings
from vigil.models.aml import (
    Alert,
    Customer,
    CustomerBaseline,
    KYCProfile,
    Transaction,
)
from vigil.models.tenant import Tenant
from vigil.models.user import User
from vigil.security.passwords import hash_password


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _days_ago(days: int) -> _dt.date:
    return _dt.date.today() - _dt.timedelta(days=days)


def _txn(ext, amount, direction, channel, cp, days):
    return {"ext": ext, "amount": amount, "direction": direction, "channel": channel, "cp": cp, "days": days}


# --- the synthetic bank (seed + eval ground truth) --------------------------

CASE_SPECS: list[dict] = [
    {
        "key": "retail_spike_fp",
        "customer": {
            "external_id": "C-1001",
            "name": "Sunrise Retail LLC",
            "entity_type": "business",
            "risk_rating": "low",
        },
        "kyc": {"occupation": "retail merchant", "pep": False, "expected_max": 60000, "channels": ["card", "ach"]},
        "alert": {
            "id": "TM-5501",
            "rule_id": "R-VOL-SPIKE",
            "reason": "daily volume spike vs 30-day average",
            "age_days": 2,
        },
        "txns": [
            _txn("TXN-1001", 45000, "credit", "card", "Card Acquirer", 4),
            _txn("TXN-1002", 12000, "credit", "ach", "Wholesale Buyer", 9),
            _txn("TXN-1003", 8000, "debit", "ach", "Supplier Co", 12),
        ],
        "ground_truth": {"disposition": "clear", "route": "auto", "label": "fp", "typologies": []},
    },
    {
        "key": "rapid_movement_layering",
        "customer": {
            "external_id": "C-1002",
            "name": "Atlas Trading Inc",
            "entity_type": "business",
            "risk_rating": "medium",
        },
        "kyc": {"occupation": "import/export", "pep": False, "expected_max": 15000, "channels": ["wire"]},
        "alert": {
            "id": "TM-5567",
            "rule_id": "R-RAPID-MOVE",
            "reason": "rapid in-then-out funds movement",
            "age_days": 1,
        },
        "txns": [
            _txn("TXN-2001", 50000, "credit", "wire", "Offshore Holding A", 8),
            _txn("TXN-2002", 20000, "debit", "wire", "Shell Co B", 7),
            _txn("TXN-2003", 18000, "debit", "wire", "Shell Co C", 6),
            _txn("TXN-2004", 11000, "debit", "wire", "Shell Co D", 5),
        ],
        "ground_truth": {"disposition": "escalate", "route": "hitl", "label": "suspicious", "typologies": ["layering"]},
    },
    {
        "key": "structuring",
        "customer": {
            "external_id": "C-1003",
            "name": "Joan Pereira",
            "entity_type": "individual",
            "risk_rating": "medium",
        },
        "kyc": {"occupation": "salaried", "pep": False, "expected_max": 8000, "channels": ["ach"]},
        "alert": {
            "id": "TM-5588",
            "rule_id": "R-STRUCT",
            "reason": "multiple cash deposits below CTR threshold",
            "age_days": 3,
        },
        "txns": [
            _txn("TXN-3001", 9200, "credit", "cash", "Cash Deposit", 9),
            _txn("TXN-3002", 9400, "credit", "cash", "Cash Deposit", 8),
            _txn("TXN-3003", 9600, "credit", "cash", "Cash Deposit", 6),
            _txn("TXN-3004", 9300, "credit", "cash", "Cash Deposit", 4),
            _txn("TXN-3005", 9500, "credit", "cash", "Cash Deposit", 2),
        ],
        "ground_truth": {
            "disposition": "escalate",
            "route": "hitl",
            "label": "suspicious",
            "typologies": ["structuring"],
        },
    },
    {
        "key": "sanctions_name_match_fp",
        "customer": {"external_id": "C-1004", "name": "John Smith", "entity_type": "individual", "risk_rating": "low"},
        "kyc": {"occupation": "teacher", "pep": False, "expected_max": 5000, "channels": ["card", "ach"]},
        "alert": {
            "id": "TM-5602",
            "rule_id": "R-SANCTIONS",
            "reason": "sanctions screening name match (common name)",
            "age_days": 1,
        },
        "txns": [
            _txn("TXN-4001", 800, "debit", "card", "Grocery Store", 10),
            _txn("TXN-4002", 1200, "debit", "ach", "Utility Co", 5),
        ],
        "ground_truth": {"disposition": "clear", "route": "auto", "label": "fp", "typologies": []},
    },
    {
        "key": "high_volume_fp",
        "customer": {
            "external_id": "C-1005",
            "name": "PayrollCo Services",
            "entity_type": "business",
            "risk_rating": "low",
        },
        "kyc": {"occupation": "payroll processor", "pep": False, "expected_max": 200000, "channels": ["ach"]},
        "alert": {"id": "TM-5610", "rule_id": "R-VOL-HIGH", "reason": "high aggregate outbound volume", "age_days": 4},
        "txns": [
            _txn("TXN-5001", 150000, "debit", "ach", "Employee Payroll Batch", 6),
            _txn("TXN-5002", 120000, "debit", "ach", "Employee Payroll Batch", 20),
        ],
        "ground_truth": {"disposition": "clear", "route": "auto", "label": "fp", "typologies": []},
    },
    {
        "key": "mule_pattern",
        "customer": {
            "external_id": "C-1006",
            "name": "Mia Lewandowski",
            "entity_type": "individual",
            "risk_rating": "high",
        },
        "kyc": {"occupation": "student", "pep": False, "expected_max": 3000, "channels": ["ach", "card"]},
        "alert": {
            "id": "TM-5623",
            "rule_id": "R-MULE",
            "reason": "many unrelated inbound payments funneled out",
            "age_days": 2,
        },
        "txns": [
            _txn("TXN-6001", 1500, "credit", "ach", "Sender Alpha", 9),
            _txn("TXN-6002", 1200, "credit", "ach", "Sender Bravo", 8),
            _txn("TXN-6003", 1800, "credit", "ach", "Sender Charlie", 8),
            _txn("TXN-6004", 900, "credit", "ach", "Sender Delta", 7),
            _txn("TXN-6005", 1100, "credit", "ach", "Sender Echo", 6),
            _txn("TXN-6006", 1300, "credit", "ach", "Sender Foxtrot", 5),
            _txn("TXN-6007", 7500, "debit", "wire", "Collector Account", 4),
        ],
        "ground_truth": {"disposition": "escalate", "route": "hitl", "label": "suspicious", "typologies": ["mule"]},
    },
    {
        "key": "dormant_reactivation_rfi",
        "customer": {
            "external_id": "C-1007",
            "name": "Opaque Holdings Ltd",
            "entity_type": "business",
            "risk_rating": "medium",
        },
        "kyc": None,  # no KYC on file → cannot baseline → RFI
        "alert": {
            "id": "TM-5634",
            "rule_id": "R-DORMANT",
            "reason": "dormant account reactivation, large credit",
            "age_days": 5,
        },
        "txns": [
            _txn("TXN-7001", 25000, "credit", "wire", "Unknown Originator", 3),
        ],
        "ground_truth": {"disposition": "need_info", "route": "hitl", "label": "rfi", "typologies": []},
    },
    {
        "key": "round_amount_fp",
        "customer": {
            "external_id": "C-1008",
            "name": "Vendor Pay LLC",
            "entity_type": "business",
            "risk_rating": "low",
        },
        "kyc": {"occupation": "B2B services", "pep": False, "expected_max": 30000, "channels": ["ach"]},
        "alert": {"id": "TM-5641", "rule_id": "R-ROUND", "reason": "repeated round-number transactions", "age_days": 6},
        "txns": [
            _txn("TXN-8001", 10000, "debit", "ach", "Recurring Vendor", 7),
            _txn("TXN-8002", 10000, "debit", "ach", "Recurring Vendor", 21),
        ],
        "ground_truth": {"disposition": "clear", "route": "auto", "label": "fp", "typologies": []},
    },
    {
        "key": "cross_border_layering",
        "customer": {
            "external_id": "C-1009",
            "name": "Global Imports Co",
            "entity_type": "business",
            "risk_rating": "high",
        },
        "kyc": {"occupation": "importer", "pep": False, "expected_max": 20000, "channels": ["wire"]},
        "alert": {"id": "TM-5655", "rule_id": "R-XBORDER", "reason": "cross-border rapid movement", "age_days": 2},
        "txns": [
            _txn("TXN-9001", 40000, "credit", "wire", "Foreign Originator X", 7),
            _txn("TXN-9002", 25000, "debit", "wire", "Foreign Beneficiary Y", 6),
            _txn("TXN-9003", 14000, "debit", "wire", "Foreign Beneficiary Z", 5),
        ],
        "ground_truth": {"disposition": "escalate", "route": "hitl", "label": "suspicious", "typologies": ["layering"]},
    },
]


def seed_demo(session: Session, settings: Settings) -> dict:
    """Idempotently seed the demo bank: officer, customers, KYC, baselines,
    transactions, and monitoring alerts."""

    tenant = session.scalars(select(Tenant).where(Tenant.slug == settings.demo_brand_slug)).first()
    if tenant is None:
        tenant = Tenant(slug=settings.demo_brand_slug, name="Meridian Bank (demo institution)")
        session.add(tenant)
        session.flush()

    if not session.scalars(select(User).where(User.email == settings.demo_admin_email)).first():
        session.add(
            User(
                tenant_id=tenant.id,
                email=settings.demo_admin_email,
                name="Demo Compliance Officer",
                password_hash=hash_password(settings.demo_admin_password),
                role="compliance_officer",
            )
        )

    now = _now()
    created = 0
    for spec in CASE_SPECS:
        c = spec["customer"]
        existing = session.scalars(
            select(Customer).where(Customer.tenant_id == tenant.id, Customer.external_id == c["external_id"])
        ).first()
        if existing is not None:
            continue
        customer = Customer(
            tenant_id=tenant.id,
            external_id=c["external_id"],
            name=c["name"],
            entity_type=c["entity_type"],
            risk_rating=c["risk_rating"],
        )
        session.add(customer)
        session.flush()

        kyc = spec.get("kyc")
        if kyc is not None:
            session.add(
                KYCProfile(
                    customer_id=customer.id,
                    occupation=kyc.get("occupation"),
                    expected_activity={"expected_max": kyc["expected_max"], "channels": kyc.get("channels", [])},
                    pep=kyc.get("pep", False),
                    adverse_media=kyc.get("adverse_media", False),
                    onboarded_at=_days_ago(400),
                )
            )
            session.add(
                CustomerBaseline(
                    customer_id=customer.id,
                    window_days=30,
                    expected_max_amount=kyc["expected_max"],
                    expected_channels=kyc.get("channels", []),
                    note="rolling 30-day expected ceiling from KYC profile",
                )
            )

        for t in spec["txns"]:
            session.add(
                Transaction(
                    tenant_id=tenant.id,
                    customer_id=customer.id,
                    external_txn_id=t["ext"],
                    amount=t["amount"],
                    direction=t["direction"],
                    channel=t["channel"],
                    counterparty_name=t["cp"],
                    occurred_on=_days_ago(t["days"]),
                )
            )

        a = spec["alert"]
        session.add(
            Alert(
                tenant_id=tenant.id,
                customer_id=customer.id,
                external_alert_id=a["id"],
                spec_key=spec["key"],
                rule_id=a["rule_id"],
                alert_reason=a["reason"],
                received_at=now,
                age_days=a.get("age_days", 0),
            )
        )
        created += 1

    session.flush()
    return {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "alerts_created": created,
        "customers": created,
    }
