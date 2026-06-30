"""Continuous suspicion scoring — the engine that makes the FP/FN trade-off real.

Vigil used to dispose in a single binary step, so "false-positive reduction at a
fixed false-negative rate" could only ever be asserted, never computed. This module
produces a continuous ``suspicion_score`` in ``[0, 1]`` per alert, which the eval
harness sweeps a threshold over to draw an actual FP-reduction-at-fixed-FN curve.

Two signals feed the score:

  * ``baseline_deviation`` — how far observed activity exceeds the customer's *own*
    expected ceiling, on a smooth ramp. Per-customer scoring (not a universal
    threshold) is how the false-positive rate actually falls: a large flow within
    the customer's established pattern reads benign; an out-of-pattern one does not.
  * the strongest evidenced typology likelihood.

The blend is bumped — by a bounded amount — for high-risk and PEP customers, so the
risk rating finally influences the decision instead of sitting unused in the
enrichment.
"""

from __future__ import annotations

from collections.abc import Sequence

from vigil.contracts.alert_scope import TypologyClaim

# Bounded upward nudges. Kept small so risk never manufactures suspicion on its own
# — it only sharpens a signal that is already there.
_RISK_WEIGHT = {"low": 0.0, "medium": 0.05, "high": 0.12}
_PEP_BUMP = 0.05


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def baseline_deviation(observed: float, expected_max: float, tolerance: float = 1.2) -> float:
    """Smooth ``0..1`` ramp of how far observed exceeds the tolerated ceiling.

    ``0`` at or under ``expected_max * tolerance``; ramps linearly to ``1.0`` once
    observed reaches roughly twice that ceiling. Continuous by design, so a
    near-baseline spike scores low and a wild one scores high — the separation the
    threshold sweep depends on. With no baseline on file, any activity is fully
    deviant (cannot be explained).
    """

    if expected_max <= 0:
        return 1.0 if observed > 0 else 0.0
    ceiling = expected_max * tolerance
    if observed <= ceiling:
        return 0.0
    return min(1.0, (observed - ceiling) / ceiling)


def suspicion_score(
    claims: Sequence[TypologyClaim],
    deviation: float,
    *,
    risk_rating: str = "low",
    pep: bool = False,
) -> float:
    """Blend the strongest evidenced typology likelihood with the baseline
    deviation, then apply a bounded risk/PEP bump. Range ``[0, 1]``."""

    typ = max((c.likelihood for c in claims if c.is_evidenced), default=0.0)
    base = max(typ, _clamp(deviation))
    bump = _RISK_WEIGHT.get((risk_rating or "low").lower(), 0.0) + (_PEP_BUMP if pep else 0.0)
    # Apply the bump in the remaining headroom so it can sharpen but never overflow.
    return round(_clamp(base + bump * (1.0 - base)), 4)
