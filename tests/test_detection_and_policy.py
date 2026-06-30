"""Unit tests for the typology detectors and the generic policy engine."""

import datetime as _dt

import pytest

from vigil.detection import detect_layering, detect_mule, detect_structuring
from vigil.models.aml import Transaction
from vigil.policy.engine import evaluate_routing


def _t(ext, amount, direction, channel="ach", cp="CP", days=5):
    return Transaction(
        external_txn_id=ext,
        amount=amount,
        direction=direction,
        channel=channel,
        counterparty_name=cp,
        occurred_on=_dt.date.today() - _dt.timedelta(days=days),
    )


@pytest.mark.unit
def test_structuring_fires_on_sub_ctr_cash_deposits():
    txns = [
        _t("T1", 9200, "credit", "cash"),
        _t("T2", 9400, "credit", "cash"),
        _t("T3", 9600, "credit", "cash"),
    ]
    claim = detect_structuring(txns)
    assert claim is not None
    assert claim.typology.value == "structuring"
    assert len(claim.evidence) == 3
    # Two deposits is not yet a pattern.
    assert detect_structuring(txns[:2]) is None
    # Non-cash sub-CTR credits do not trip structuring.
    assert detect_structuring([_t("T4", 9500, "credit", "ach") for _ in range(4)]) is None


@pytest.mark.unit
def test_layering_fires_on_rapid_in_then_out():
    txns = [
        _t("T1", 50000, "credit", "wire"),
        _t("T2", 20000, "debit", "wire"),
        _t("T3", 18000, "debit", "wire"),
        _t("T4", 11000, "debit", "wire"),
    ]
    claim = detect_layering(txns)
    assert claim is not None
    assert claim.typology.value == "layering"
    assert claim.evidence  # bound transactions
    # A single large credit with no outflow is not layering.
    assert detect_layering([_t("T1", 50000, "credit", "wire")]) is None


@pytest.mark.unit
def test_mule_fires_on_many_small_inbounds_funneled_out():
    txns = [_t(f"C{i}", 1200, "credit", "ach", cp=f"Sender {i}") for i in range(6)]
    txns.append(_t("D1", 7000, "debit", "wire", cp="Collector"))
    claim = detect_mule(txns)
    assert claim is not None
    assert claim.typology.value == "mule"
    # Fewer than five distinct senders → no funnel pattern.
    few = [_t(f"C{i}", 1200, "credit", "ach", cp=f"Sender {i}") for i in range(3)]
    few.append(_t("D1", 3000, "debit", "wire", cp="Collector"))
    assert detect_mule(few) is None


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
