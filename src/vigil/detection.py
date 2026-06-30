"""Typology detection + baseline assessment — deterministic, inspectable, pure.

Each detector reads the customer's transaction lookback and, when its pattern
fires, returns a ``TypologyClaim`` with **every claim bound to the transactions
that prove it**. Thresholds come from the versioned, content-hashed typology
library (``typology_library.py``) — data, not constants — so a tenant can tune them
and an examiner can pin the exact parameters behind a disposition.

Detection is **window-scoped**: each typology only looks back over its own
``window_days`` relative to the alert date, so a customer clean now does not flag
for activity from long ago (and the read stays bounded at scale). The baseline
assessment compares observed vs. the customer's own expected ceiling — per-customer
scoring (not a universal threshold) is *how* AI cuts the false-positive rate.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Sequence

from vigil.contracts.alert_scope import TxnCitation, TypologyClaim
from vigil.models.aml import CustomerBaseline, Transaction
from vigil.models.enums import TxnDirection, Typology
from vigil.typology_library import TypologyLibrary, get_library


def _amt(t: Transaction) -> float:
    return float(t.amount)


def _within(txns: Sequence[Transaction], days: int, as_of: _dt.date) -> list[Transaction]:
    """Transactions whose ``occurred_on`` falls within ``days`` before ``as_of``."""

    cutoff = as_of - _dt.timedelta(days=int(days))
    return [t for t in txns if t.occurred_on and t.occurred_on >= cutoff]


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


def detect_structuring(txns: Sequence[Transaction], params: dict, *, as_of: _dt.date) -> TypologyClaim | None:
    floor = float(params.get("floor", 9_000.0))
    ceiling = float(params.get("ceiling", 10_000.0))
    min_count = int(params.get("min_count", 3))
    channels = {c.lower() for c in params.get("channels", ["cash"])}
    window = _within(txns, params.get("window_days", 30), as_of)

    hits = [
        t
        for t in window
        if t.direction == TxnDirection.CREDIT.value
        and (t.channel or "").lower() in channels
        and floor <= _amt(t) < ceiling
    ]
    if len(hits) < min_count:
        return None
    total = sum(_amt(t) for t in hits)
    # Monotonic in count past the threshold, so a borderline 3-deposit pattern
    # scores lower than a blatant 8-deposit one (the sweep needs that spread).
    over = len(hits) - min_count
    likelihood = round(min(0.95, 0.62 + 0.06 * over + 0.03 * min_count), 2)
    return TypologyClaim(
        typology=Typology.STRUCTURING,
        likelihood=likelihood,
        rationale=(
            f"{len(hits)} cash deposits between ${floor:,.0f} and ${ceiling:,.0f} "
            f"(just under the CTR threshold) totaling ${total:,.0f} — consistent with structuring."
        ),
        evidence=[_cite(t) for t in hits],
    )


def detect_layering(txns: Sequence[Transaction], params: dict, *, as_of: _dt.date) -> TypologyClaim | None:
    min_total_in = float(params.get("min_total_in", 20_000.0))
    movement_ratio = float(params.get("movement_ratio", 0.7))
    min_outflows = int(params.get("min_outflows", 2))
    require_out_after_in = bool(params.get("require_out_after_in", True))
    window = _within(txns, params.get("window_days", 14), as_of)

    inflows = [t for t in window if t.direction == TxnDirection.CREDIT.value]
    outflows = [t for t in window if t.direction == TxnDirection.DEBIT.value]

    # Real layering is *in then out*: only count outflows on/after the first inflow.
    # Without this, large debits followed by unrelated later credits false-flag.
    if require_out_after_in and inflows:
        first_in = min(t.occurred_on for t in inflows)
        outflows = [t for t in outflows if t.occurred_on >= first_in]

    total_in = sum(_amt(t) for t in inflows)
    total_out = sum(_amt(t) for t in outflows)
    if total_in < min_total_in or total_out < movement_ratio * total_in or len(outflows) < min_outflows:
        return None
    ratio = total_out / max(total_in, 1.0)
    big = sorted(inflows, key=_amt, reverse=True)[:3] + sorted(outflows, key=_amt, reverse=True)[:3]
    return TypologyClaim(
        typology=Typology.LAYERING,
        likelihood=round(min(0.95, 0.6 + ratio * 0.25), 2),
        rationale=(
            f"${total_in:,.0f} received and ${total_out:,.0f} moved out within the lookback "
            f"({len(outflows)} outbound transfers, {ratio * 100:.0f}% of inflow) — "
            f"rapid in-then-out consistent with layering."
        ),
        evidence=[_cite(t) for t in big],
    )


def detect_mule(txns: Sequence[Transaction], params: dict, *, as_of: _dt.date) -> TypologyClaim | None:
    max_small = float(params.get("max_small_credit", 2_000.0))
    min_distinct = int(params.get("min_distinct_senders", 5))
    window = _within(txns, params.get("window_days", 30), as_of)

    small_credits = [
        t for t in window if t.direction == TxnDirection.CREDIT.value and _amt(t) < max_small and t.counterparty_name
    ]
    distinct = {t.counterparty_name for t in small_credits}
    debits = [t for t in window if t.direction == TxnDirection.DEBIT.value]
    if len(distinct) < min_distinct or not debits:
        return None
    lump = max(debits, key=_amt)
    over = len(distinct) - min_distinct
    likelihood = round(min(0.92, 0.62 + 0.05 * min_distinct + 0.03 * over), 2)
    return TypologyClaim(
        typology=Typology.MULE,
        likelihood=likelihood,
        rationale=(
            f"{len(small_credits)} small inbound payments from {len(distinct)} unrelated counterparties "
            f"funneled into a ${_amt(lump):,.0f} outbound transfer — consistent with a money-mule funnel."
        ),
        evidence=[_cite(t) for t in small_credits[:6]] + [_cite(lump)],
    )


_DETECTORS = (
    ("structuring", detect_structuring),
    ("layering", detect_layering),
    ("mule", detect_mule),
)


def detect_typologies(
    txns: Sequence[Transaction],
    library: TypologyLibrary | None = None,
    *,
    as_of: _dt.date | None = None,
) -> list[TypologyClaim]:
    """Run every detector with its library parameters over the windowed lookback."""

    lib = library or get_library()
    when = as_of or _dt.date.today()
    claims = [fn(txns, lib.params(name), as_of=when) for name, fn in _DETECTORS]
    return [c for c in claims if c is not None]


def assess_baseline(
    txns: Sequence[Transaction],
    baseline: CustomerBaseline | None,
    tolerance: float = 1.2,
) -> tuple[float, float, bool]:
    """Return ``(observed_amount, expected_max, baseline_explained)``.

    Observed is the largest single transaction (a window proxy) so a legitimate-but-
    large recurring flow within the customer's own ceiling reads as explained, while
    an out-of-pattern spike does not. ``tolerance`` is the multiple of the expected
    ceiling still treated as explained.
    """

    observed = max((_amt(t) for t in txns), default=0.0)
    expected_max = float(baseline.expected_max_amount) if baseline else 0.0
    explained = bool(baseline) and observed <= expected_max * tolerance
    return observed, expected_max, explained
