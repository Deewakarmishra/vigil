"""Unit tests for the suspicion score, the FP@FN sweep, the typology library, and MCP."""

import importlib.util

import pytest

from vigil.contracts.alert_scope import TxnCitation, TypologyClaim
from vigil.eval.metrics import sweep_fp_at_zero_fn
from vigil.models.enums import Typology
from vigil.scoring import baseline_deviation, suspicion_score
from vigil.typology_library import load_library


def _claim(likelihood: float) -> TypologyClaim:
    return TypologyClaim(
        typology=Typology.STRUCTURING,
        likelihood=likelihood,
        evidence=[TxnCitation(transaction_id="t1", locator="Txn T1", quote="+$9,500", amount=9500)],
    )


# ---- scoring ---------------------------------------------------------------


@pytest.mark.unit
def test_baseline_deviation_ramps_smoothly():
    # Within the tolerated ceiling → no deviation.
    assert baseline_deviation(5000, 10000, tolerance=1.2) == 0.0
    assert baseline_deviation(12000, 10000, tolerance=1.2) == 0.0
    # Beyond it, a smooth ramp that saturates at 1.0.
    assert 0.0 < baseline_deviation(18000, 10000, tolerance=1.2) < 1.0
    assert baseline_deviation(100000, 10000, tolerance=1.2) == 1.0
    # No baseline on file → fully deviant.
    assert baseline_deviation(100, 0) == 1.0


@pytest.mark.unit
def test_suspicion_score_is_monotonic_and_risk_weighted():
    # A stronger typology yields a higher score.
    assert suspicion_score([_claim(0.9)], 0.0) > suspicion_score([_claim(0.6)], 0.0)
    # Baseline deviation alone produces suspicion even with no typology.
    assert suspicion_score([], 0.8) == pytest.approx(0.8, abs=0.01)
    # Risk + PEP only sharpen an existing signal, never exceed 1.0.
    low = suspicion_score([_claim(0.6)], 0.0, risk_rating="low", pep=False)
    high = suspicion_score([_claim(0.6)], 0.0, risk_rating="high", pep=True)
    assert high > low <= 1.0
    assert suspicion_score([_claim(0.95)], 1.0, risk_rating="high", pep=True) <= 1.0


# ---- the FP@FN sweep -------------------------------------------------------


def _rec(label, score, **kw):
    base = {"gt_label": label, "score": score}
    base.update(kw)
    return base


@pytest.mark.unit
def test_sweep_finds_max_fp_reduction_at_zero_false_negatives():
    records = [
        _rec("fp", 0.02),
        _rec("fp", 0.05),
        _rec("fp", 0.10),
        _rec("suspicious", 0.85),
        _rec("suspicious", 0.92),
    ]
    out = sweep_fp_at_zero_fn(records)
    # All FPs separable below the suspicious cluster → 100% reduction, zero FN.
    assert out["fp_reduction_at_zero_fn"] == 1.0
    assert out["operating_threshold"] <= 0.85
    assert out["separation_margin"] == pytest.approx(0.75, abs=0.01)
    # Every point of the curve at/under the operating threshold has zero FN.
    for pt in out["curve"]:
        if pt["threshold"] <= out["operating_threshold"]:
            assert pt["false_negatives"] == 0


@pytest.mark.unit
def test_sweep_never_reports_a_false_negative_at_the_operating_point():
    # A suspicious item scoring low must cap the operating threshold below it.
    records = [_rec("fp", 0.1), _rec("fp", 0.4), _rec("suspicious", 0.3)]
    out = sweep_fp_at_zero_fn(records)
    assert out["operating_threshold"] <= 0.3
    # Only the FP below 0.3 can be cleared without a false negative → 50% reduction.
    assert out["fp_reduction_at_zero_fn"] == 0.5


# ---- the typology library --------------------------------------------------


@pytest.mark.unit
def test_library_loads_with_stable_content_hash(tmp_path):
    a = load_library()
    b = load_library()
    assert a.content_hash == b.content_hash  # deterministic
    assert len(a.content_hash) == 64
    assert {"structuring", "layering", "mule"}.issubset(set(a.typologies))
    assert a.params("structuring")["min_count"] >= 1


@pytest.mark.unit
def test_library_hash_changes_when_a_parameter_changes(tmp_path):
    p = tmp_path / "library.yaml"
    p.write_text("version: t1\ntypologies:\n  structuring: {min_count: 3}\n")
    lib1 = load_library(p)
    p.write_text("version: t1\ntypologies:\n  structuring: {min_count: 4}\n")
    lib2 = load_library(p)
    assert lib1.content_hash != lib2.content_hash


@pytest.mark.unit
def test_library_falls_back_to_defaults_when_yaml_missing(tmp_path):
    lib = load_library(tmp_path / "does-not-exist.yaml")
    assert "structuring" in lib.typologies


# ---- MCP (optional extra) --------------------------------------------------


@pytest.mark.unit
def test_mcp_server_imports_when_extra_present():
    if importlib.util.find_spec("mcp") is None:
        pytest.skip("mcp extra not installed")
    from vigil import mcp_server

    assert mcp_server.mcp is not None
