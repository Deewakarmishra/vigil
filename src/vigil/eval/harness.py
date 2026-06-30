"""Run the backtest: replay the agent over seeded alerts, score vs ground truth.

Eval is read-only over the agent (it builds the scope + routing decision without
persisting actions), so it is deterministic and side-effect free apart from the
EvalRun + EvalCase rows. Per-alert ground truth comes straight from ``CASE_SPECS``,
so the showcase and the backtest can never silently disagree.
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from vigil.agent.context import AlertContext
from vigil.agent.loop import build_alert_scope
from vigil.agent.runner import _load_rules
from vigil.eval.metrics import compute_metrics
from vigil.models.aml import Alert
from vigil.models.evaluation import EvalCase, EvalRun
from vigil.models.tenant import Tenant
from vigil.policy.engine import evaluate_routing
from vigil.synthetic.generator import CASE_SPECS


def run_eval(session: Session, tenant_slug: str) -> tuple[dict, list[dict]]:
    tenant = session.scalars(select(Tenant).where(Tenant.slug == tenant_slug)).first()
    if tenant is None:
        raise ValueError(f"tenant {tenant_slug} not seeded — run `vigil demo` first")
    rules = _load_rules(session, tenant.id)
    by_key = {s["key"]: s for s in CASE_SPECS}

    records: list[dict] = []
    for alert in session.scalars(select(Alert).where(Alert.tenant_id == tenant.id)):
        spec = by_key.get(alert.spec_key)
        if spec is None:
            continue
        gt = spec["ground_truth"]
        ctx = AlertContext.load(session, alert.id)
        scope, facts = build_alert_scope(ctx)
        decision = evaluate_routing(rules, facts)

        evidenced = scope.evidenced_hypotheses
        records.append(
            {
                "key": spec["key"],
                "pred_disposition": scope.disposition.value,
                "pred_route": decision.route,
                "pred_typologies": [h.typology.value for h in evidenced],
                "score": scope.enrichment.suspicion_score,
                "claim_count": len(scope.hypotheses),
                "claim_cited": sum(1 for h in scope.hypotheses if h.is_evidenced),
                "has_sar": bool(scope.sar),
                "sar_complete": bool(scope.sar and scope.sar.is_complete),
                "gt_disposition": gt["disposition"],
                "gt_route": gt["route"],
                "gt_label": gt["label"],
                "gt_typologies": gt["typologies"],
            }
        )

    metrics = compute_metrics(records)
    run = EvalRun(started_at=_dt.datetime.now(_dt.UTC), dataset_name="synthetic-v1", metrics=metrics)
    session.add(run)
    session.flush()
    for r in records:
        session.add(
            EvalCase(
                eval_run_id=run.id,
                case_ref=r["key"],
                predictions={
                    "disposition": r["pred_disposition"],
                    "route": r["pred_route"],
                    "typologies": r["pred_typologies"],
                },
                ground_truth={
                    "disposition": r["gt_disposition"],
                    "route": r["gt_route"],
                    "label": r["gt_label"],
                },
                scores={
                    "disposition_ok": r["pred_disposition"] == r["gt_disposition"],
                    "route_ok": r["pred_route"] == r["gt_route"],
                    "false_negative": r["gt_label"] == "suspicious" and r["pred_disposition"] == "clear",
                },
            )
        )
    session.flush()
    return metrics, records
