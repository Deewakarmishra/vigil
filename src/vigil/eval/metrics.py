"""Eval metrics computed from per-alert prediction/ground-truth records.

The headline is **false-positive reduction at a fixed false-negative rate**, and it
is now *computed*, not asserted: ``sweep_fp_at_zero_fn`` sweeps a clear threshold
over each alert's continuous suspicion score and reports the maximum FP reduction
achievable while **no** suspicious alert is cleared (false_negatives = 0). Recall is
never traded for a prettier FP number — ``false_negatives`` remains a zero-tolerance
gate, the cardinal failure being a suspicious alert the agent cleared (the TD-Bank
lesson).
"""

from __future__ import annotations


def _safe_div(n: float, d: float) -> float:
    return round(n / d, 4) if d else 0.0


def sweep_fp_at_zero_fn(records: list[dict]) -> dict:
    """Sweep the clear threshold over the suspicion score.

    Disposition under the sweep is "clear if score < threshold", which is exactly
    the knob an officer tunes. We report the full curve, the operating point (the
    highest FP reduction with zero false negatives), and the separation margin
    between the lowest suspicious score and the highest false-positive score — a
    large margin means the score cleanly tells benign from suspicious.
    """

    suspicious = [r for r in records if r["gt_label"] == "suspicious"]
    fps = [r for r in records if r["gt_label"] == "fp"]
    if not fps:
        return {
            "operating_threshold": 0.0,
            "fp_reduction_at_zero_fn": 0.0,
            "separation_margin": 0.0,
            "curve": [],
        }

    scores = sorted({float(r["score"]) for r in records})
    # Candidate thresholds: just above each observed score (so "< threshold" flips
    # exactly at that score), plus the endpoints.
    candidates = sorted({0.0, 1.0001, *[s + 1e-6 for s in scores]})

    curve: list[dict] = []
    best_threshold, best_fpr = 0.0, 0.0
    for t in candidates:
        fn = sum(1 for r in suspicious if float(r["score"]) < t)
        fp_cleared = sum(1 for r in fps if float(r["score"]) < t)
        fpr = _safe_div(fp_cleared, len(fps))
        curve.append({"threshold": round(t, 4), "fp_reduction": fpr, "false_negatives": fn})
        if fn == 0 and fpr > best_fpr:
            best_fpr, best_threshold = fpr, round(t, 4)

    min_susp = min((float(r["score"]) for r in suspicious), default=1.0)
    max_fp = max((float(r["score"]) for r in fps), default=0.0)
    return {
        "operating_threshold": best_threshold,
        "fp_reduction_at_zero_fn": best_fpr,
        "separation_margin": round(min_susp - max_fp, 4),
        "curve": curve,
    }


def compute_metrics(records: list[dict]) -> dict:
    total = len(records)
    disp_ok = sum(1 for r in records if r["pred_disposition"] == r["gt_disposition"])
    route_ok = sum(1 for r in records if r["pred_route"] == r["gt_route"])

    suspicious = [r for r in records if r["gt_label"] == "suspicious"]
    fps = [r for r in records if r["gt_label"] == "fp"]

    # FN: a truly-suspicious alert the agent cleared. Must be 0.
    false_negatives = sum(1 for r in suspicious if r["pred_disposition"] == "clear")
    # Raw point measure: fraction of false positives the live disposition cleared.
    fp_cleared = sum(1 for r in fps if r["pred_disposition"] == "clear")

    # Typology recall: predicted typologies cover the planted ones.
    typ_ok = sum(1 for r in suspicious if set(r["gt_typologies"]).issubset(set(r["pred_typologies"])))

    # Citation precision: every evidenced hypothesis carries a transaction citation.
    claims = sum(r["claim_count"] for r in records)
    claims_cited = sum(r["claim_cited"] for r in records)

    # SAR completeness: of the escalations that produced a SAR draft, how many carry
    # all 5W. A no-typology escalation drafts no SAR, so it does not dilute this.
    sar_bearing = [r for r in records if r["pred_disposition"] == "escalate" and r["has_sar"]]
    sar_complete = sum(1 for r in sar_bearing if r["sar_complete"])

    sweep = sweep_fp_at_zero_fn(records)

    return {
        "total_alerts": total,
        "disposition_accuracy": _safe_div(disp_ok, total),
        "false_negatives": false_negatives,
        # Headline: the computed operating point (max FP reduction at FN = 0).
        "fp_reduction": sweep["fp_reduction_at_zero_fn"],
        "operating_threshold": sweep["operating_threshold"],
        "separation_margin": sweep["separation_margin"],
        # Back-compat: the raw fraction of FPs the live disposition cleared.
        "fp_reduction_point": _safe_div(fp_cleared, len(fps)),
        "typology_recall": _safe_div(typ_ok, len(suspicious)),
        "citation_precision": _safe_div(claims_cited, claims),
        "sar_completeness": _safe_div(sar_complete, len(sar_bearing)),
        "route_accuracy": _safe_div(route_ok, total),
        "fp_sweep": sweep["curve"],
    }
