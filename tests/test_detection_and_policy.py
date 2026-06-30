"""Unit tests for the typology detectors (library-driven, windowed) and the policy engine."""

import datetime as _dt

import pytest

from vigil.detection import detect_layering, detect_mule, detect_structuring, detect_typologies
from vigil.models.aml import Transaction
from vigil.policy.engine import evaluate_routing
from vigil.typology_library import get_library

_LIB = get_library()
_TODAY = _dt.date.today()


def _t(ext, amount, direction, channel="ach", cp="CP", days=5):
    return Transaction(
        external_txn_id=ext,
        amount=amount,
        direction=direction,
        channel=channel,
        counterparty_name=cp,
        occurred_on=_dt.date.today() - _dt.timedelta(days=days),
    )


def _p(name):
    return _LIB.params(name)


@pytest.mark.unit
def test_structuring_fires_on_sub_ctr_cash_deposits():
    txns = [
        _t("T1", 9200, "credit", "cash"),
        _t("T2", 9400, "credit", "cash"),
        _t("T3", 9600, "credit", "cash"),
    ]
    claim = detect_structuring(txns, _p("structuring"), as_of=_TODAY)
    assert claim is not None
    assert claim.typology.value == "structuring"
    assert len(claim.evidence) == 3
    # Two deposits is not yet a pattern.
    assert detect_structuring(txns[:2], _p("structuring"), as_of=_TODAY) is None
    # Non-cash sub-CTR credits do not trip structuring.
    assert (
        detect_structuring([_t("T4", 9500, "credit", "ach") for _ in range(4)], _p("structuring"), as_of=_TODAY) is None
    )


@pytest.mark.unit
def test_structuring_likelihood_is_monotonic_in_count():
    """A blatant pattern must score at least as high as a borderline one (sweep needs the spread)."""
    three = [_t(f"T{i}", 9500, "credit", "cash") for i in range(3)]
    eight = [_t(f"T{i}", 9500, "credit", "cash") for i in range(8)]
    c3 = detect_structuring(three, _p("structuring"), as_of=_TODAY)
    c8 = detect_structuring(eight, _p("structuring"), as_of=_TODAY)
    assert c8.likelihood >= c3.likelihood


@pytest.mark.unit
def test_detectors_respect_the_lookback_window():
    """A structuring pattern entirely outside the window must not fire."""
    old = [_t(f"T{i}", 9500, "credit", "cash", days=400) for i in range(4)]
    assert detect_structuring(old, _p("structuring"), as_of=_TODAY) is None
    # The same pattern inside the window does fire.
    recent = [_t(f"T{i}", 9500, "credit", "cash", days=3) for i in range(4)]
    assert detect_structuring(recent, _p("structuring"), as_of=_TODAY) is not None


@pytest.mark.unit
def test_layering_fires_on_rapid_in_then_out():
    txns = [
        _t("T1", 50000, "credit", "wire", days=8),
        _t("T2", 20000, "debit", "wire", days=7),
        _t("T3", 18000, "debit", "wire", days=6),
        _t("T4", 11000, "debit", "wire", days=5),
    ]
    claim = detect_layering(txns, _p("layering"), as_of=_TODAY)
    assert claim is not None
    assert claim.typology.value == "layering"
    assert claim.evidence  # bound transactions
    # A single large credit with no outflow is not layering.
    assert detect_layering([_t("T1", 50000, "credit", "wire")], _p("layering"), as_of=_TODAY) is None


@pytest.mark.unit
def test_layering_requires_outflows_after_inflow():
    """Large debits that precede the inflow are not in-then-out layering (FP fix)."""
    txns = [
        _t("D1", 20000, "debit", "wire", days=10),
        _t("D2", 18000, "debit", "wire", days=9),
        _t("C1", 50000, "credit", "wire", days=2),  # credit arrives *after* the debits
    ]
    assert detect_layering(txns, _p("layering"), as_of=_TODAY) is None
    # Reorder so the outflows follow the inflow → genuine layering.
    txns2 = [
        _t("C1", 50000, "credit", "wire", days=10),
        _t("D1", 20000, "debit", "wire", days=9),
        _t("D2", 18000, "debit", "wire", days=8),
    ]
    assert detect_layering(txns2, _p("layering"), as_of=_TODAY) is not None


@pytest.mark.unit
def test_mule_fires_on_many_small_inbounds_funneled_out():
    txns = [_t(f"C{i}", 1200, "credit", "ach", cp=f"Sender {i}") for i in range(6)]
    txns.append(_t("D1", 7000, "debit", "wire", cp="Collector"))
    claim = detect_mule(txns, _p("mule"), as_of=_TODAY)
    assert claim is not None
    assert claim.typology.value == "mule"
    # Fewer than five distinct senders → no funnel pattern.
    few = [_t(f"C{i}", 1200, "credit", "ach", cp=f"Sender {i}") for i in range(3)]
    few.append(_t("D1", 3000, "debit", "wire", cp="Collector"))
    assert detect_mule(few, _p("mule"), as_of=_TODAY) is None


@pytest.mark.unit
def test_detect_typologies_runs_the_whole_library():
    txns = [_t(f"T{i}", 9500, "credit", "cash") for i in range(4)]
    claims = detect_typologies(txns, _LIB, as_of=_TODAY)
    assert {c.typology.value for c in claims} == {"structuring"}


@pytest.mark.unit
def test_policy_recall_protection_order():
    rules = [
        {"id": "typology", "when": {"typology_likely": True}, "route": "hitl", "reason": "escalate"},
        {"id": "missing-kyc", "when": {"has_kyc": False}, "route": "hitl", "reason": "rfi"},
        {"id": "baseline", "when": {"baseline_explained": True}, "route": "auto", "reason": "clear"},
        {"id": "def", "when": {}, "route": "hitl", "reason": "review"},
    ]
    # An evidenced typology escalates even if the baseline would otherwise explain it.
    assert (
        evaluate_routing(rules, {"typology_likely": True, "baseline_explained": True, "has_kyc": True}).matched_rule_id
        == "typology"
    )
    # No typology, no KYC → RFI before any clear.
    assert evaluate_routing(rules, {"has_kyc": False, "baseline_explained": True}).matched_rule_id == "missing-kyc"
    # Clean baseline-explained FP auto-clears.
    assert evaluate_routing(rules, {"has_kyc": True, "baseline_explained": True}).route == "auto"
