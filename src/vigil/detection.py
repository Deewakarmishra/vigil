"""Typology detection + baseline assessment — deterministic, inspectable, pure.

Each detector reads the customer's transaction lookback and, when its pattern
fires, returns a ``TypologyClaim`` with **every claim bound to the transactions
that prove it**. The baseline assessment compares observed vs. the customer's own
expected ceiling — per-customer scoring (not a universal threshold) is *how* AI
cuts the false-positive rate. pg_trgm + pgvector are the production swap behind
the retrieval; the typology library here is the auditable, content-hashed core.
"""

from __future__ import annotations

from collections.abc import Sequence

from vigil.contracts.alert_scope import TxnCitation, TypologyClaim
from vigil.models.aml import CustomerBaseline, Transaction
from vigil.models.enums import TxnDirection, Typology

# CTR reporting threshold; structuring is staying just beneath it.
CTR_THRESHOLD = 10_000.0
_STRUCTURING_FLOOR = 9_000.0


def _amt(t: Transaction) -> float:
    return float(t.amount)


def _cite(t: Transaction) -> TxnCitation:
    sign = "+" if t.direction == TxnDirection.CREDIT.value else "-"
    cp = f" {t.direction} {t.counterparty_name}" if t.counterparty_name else f" {t.direction}"
    return TxnCitation(
        transaction_id=str(t.id),
        locator=f"Txn {t.external_txn_id}",
        quote=f"{sign}${_amt(t):,.0f} {t.channel or ''}{cp} on {t.occurred_on.isoformat()}".strip(),
        amount=_amt(t),
        occurred_on=t.occurred_on.isoformat(),
    )


def detect_structuring(txns: Sequence[Transaction]) -> TypologyClaim | None:
    hits = [
        t
        for t in txns
        if t.direction == TxnDirection.CREDIT.value
        and (t.channel or "").lower() == "cash"
        and _STRUCTURING_FLOOR <= _amt(t) < CTR_THRESHOLD
    ]
    if len(hits) < 3:
        return None
    total = sum(_amt(t) for t in hits)
    return TypologyClaim(
        typology=Typology.STRUCTURING,
        likelihood=round(min(0.95, 0.6 + 0.08 * len(hits)), 2),
        rationale=(
            f"{len(hits)} cash deposits between ${_STRUCTURING_FLOOR:,.0f} and ${CTR_THRESHOLD:,.0f} "
            f"(just under the CTR threshold) totaling ${total:,.0f} — consistent with structuring."
        ),
        evidence=[_cite(t) for t in hits],
    )


def detect_layering(txns: Sequence[Transaction]) -> TypologyClaim | None:
    inflows = [t for t in txns if t.direction == TxnDirection.CREDIT.value]
    outflows = [t for t in txns if t.direction == TxnDirection.DEBIT.value]
    total_in = sum(_amt(t) for t in inflows)
    total_out = sum(_amt(t) for t in outflows)
    if total_in < 20_000 or total_out < 0.7 * total_in or len(outflows) < 2:
        return None
    big = sorted(inflows, key=_amt, reverse=True)[:3] + sorted(outflows, key=_amt, reverse=True)[:3]
    return TypologyClaim(
        typology=Typology.LAYERING,
        likelihood=round(min(0.95, 0.65 + total_out / max(total_in, 1) * 0.2), 2),
        rationale=(
            f"${total_in:,.0f} received and ${total_out:,.0f} moved out within the lookback "
            f"({len(outflows)} outbound transfers) — rapid in-then-out consistent with layering."
        ),
        evidence=[_cite(t) for t in big],
    )


def detect_mule(txns: Sequence[Transaction]) -> TypologyClaim | None:
    small_credits = [
        t for t in txns if t.direction == TxnDirection.CREDIT.value and _amt(t) < 2_000 and t.counterparty_name
    ]
    distinct = {t.counterparty_name for t in small_credits}
    debits = [t for t in txns if t.direction == TxnDirection.DEBIT.value]
    if len(distinct) < 5 or not debits:
        return None
    lump = max(debits, key=_amt)
    return TypologyClaim(
        typology=Typology.MULE,
        likelihood=round(min(0.92, 0.6 + 0.05 * len(distinct)), 2),
        rationale=(
            f"{len(small_credits)} small inbound payments from {len(distinct)} unrelated counterparties "
            f"funneled into a ${_amt(lump):,.0f} outbound transfer — consistent with a money-mule funnel."
        ),
        evidence=[_cite(t) for t in small_credits[:6]] + [_cite(lump)],
    )


_DETECTORS = (detect_structuring, detect_layering, detect_mule)


def detect_typologies(txns: Sequence[Transaction]) -> list[TypologyClaim]:
    claims = [d(txns) for d in _DETECTORS]
    return [c for c in claims if c is not None]


def assess_baseline(txns: Sequence[Transaction], baseline: CustomerBaseline | None) -> tuple[float, float, bool]:
    """Return ``(observed_amount, expected_max, baseline_explained)``.

    Observed is the largest single-window proxy (max single transaction) so a
    legitimate-but-large recurring flow within the customer's own ceiling reads as
    explained, while an out-of-pattern spike does not.
    """

    observed = max((_amt(t) for t in txns), default=0.0)
    expected_max = float(baseline.expected_max_amount) if baseline else 0.0
    explained = bool(baseline) and observed <= expected_max * 1.2
    return observed, expected_max, explained
