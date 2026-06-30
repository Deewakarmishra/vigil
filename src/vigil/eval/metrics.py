"""Eval metrics computed from per-alert prediction/ground-truth records.

The headline is **false-positive reduction at a fixed false-negative rate**:
recall is never traded for a prettier FP number, so ``false_negatives`` is a
zero-tolerance gate — a suspicious alert that the agent cleared is the cardinal
failure (the TD-Bank lesson).
"""

from __future__ import annotations


def _safe_div(n: float, d: float) -> float:
    return round(n / d, 4) if d else 0.0


def compute_metrics(records: list[dict]) -> dict:
    total = len(records)
    disp_ok = sum(1 for r in records if r["pred_disposition"] == r["gt_disposition"])
    route_ok = sum(1 for r in records if r["pred_route"] == r["gt_route"])

    suspicious = [r for r in records if r["gt_label"] == "suspicious"]
    fps = [r for r in records if r["gt_label"] == "fp"]

    # FN: a truly-suspicious alert the agent cleared. Must be 0.
    false_negatives = sum(1 for r in suspicious if r["pred_disposition"] == "clear")
    # FP reduction: fraction of false positives auto-cleared.
    fp_cleared = sum(1 for r in fps if r["pred_disposition"] == "clear")

    # Typology recall: predicted typologies cover the planted ones.
    typ_ok = sum(1 for r in suspicious if set(r["gt_typologies"]).issubset(set(r["pred_typologies"])))

    # Citation precision: every evidenced hypothesis carries a transaction citation.
    claims = sum(r["claim_count"] for r in records)
    claims_cited = sum(r["claim_cited"] for r in records)

    # SAR completeness: escalations whose draft has all 5W elements.
    escalations = [r for r in records if r["pred_disposition"] == "escalate"]
    sar_complete = sum(1 for r in escalations if r["sar_complete"])

    return {
        "total_alerts": total,
        "disposition_accuracy": _safe_div(disp_ok, total),
        "false_negatives": false_negatives,
        "fp_reduction": _safe_div(fp_cleared, len(fps)),
        "typology_recall": _safe_div(typ_ok, len(suspicious)),
        "citation_precision": _safe_div(claims_cited, claims),
        "sar_completeness": _safe_div(sar_complete, len(escalations)),
        "route_accuracy": _safe_div(route_ok, total),
    }
