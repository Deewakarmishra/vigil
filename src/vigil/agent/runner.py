"""Runner: build the scope, route it, act, and audit.

On the ``auto`` route the agent **auto-clears** a false positive — always writing
a full cited rationale into the disposition's reasoning trace (never a silent
drop, the TD-Bank failure mode). On ``hitl`` it **escalates** to the officer queue
with a drafted SAR, or opens an **RFI** task. The agent never files a SAR and
never restricts an account — every typology claim is persisted with its citation
join row, and every outcome writes a hash-chained audit row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from vigil.adapters import build_adapters
from vigil.agent.context import AlertContext
from vigil.agent.loop import build_alert_scope
from vigil.contracts.alert_scope import AlertScope
from vigil.models.aml import (
    Alert,
    AlertEvidence,
    DispositionRecord,
    SARDraft,
    TypologyHypothesis,
)
from vigil.models.enums import AlertStatus, DecisionAction, ReviewStatus
from vigil.models.policy import PolicyDefinition, PolicyVersion
from vigil.models.review import ReviewTask
from vigil.policy.engine import evaluate_routing
from vigil.services.audit import write_audit

# Default routing used when a tenant has no PolicyDefinition yet. Mirrors
# policies/routing.yaml. First match wins; an empty `when` is the default.
# `route: auto` = the agent disposed (auto-clear with a stored cited rationale);
# `route: hitl` = a compliance officer must dispose (escalation) or supply info.
DEFAULT_RULES: list[dict] = [
    {
        "id": "typology-likely",
        "when": {"typology_likely": True},
        "route": "hitl",
        "reason": "evidenced typology — escalate to officer with SAR draft",
    },
    {
        "id": "missing-kyc",
        "when": {"has_kyc": False},
        "route": "hitl",
        "reason": "no KYC on file — request-for-information",
    },
    {
        "id": "baseline-explained",
        "when": {"baseline_explained": True},
        "route": "auto",
        "reason": "within customer baseline, no typology — auto-clear with stored rationale",
    },
    {
        "id": "low-confidence",
        "when": {"confidence_below": 0.6},
        "route": "hitl",
        "reason": "low confidence — officer review",
    },
    {"id": "default-escalate", "when": {}, "route": "hitl", "reason": "unexplained — officer review"},
]


@dataclass
class ResolveResult:
    scope: AlertScope
    route: str
    matched_rule_id: str
    reason: str
    outcome: str
    refs: dict = field(default_factory=dict)


def _load_rules(session: Session, tenant_id: uuid.UUID) -> list[dict]:
    pd = session.scalars(select(PolicyDefinition).where(PolicyDefinition.tenant_id == tenant_id)).first()
    if pd is None:
        return DEFAULT_RULES
    pv = session.scalars(
        select(PolicyVersion).where(PolicyVersion.policy_id == pd.id, PolicyVersion.version == pd.active_version)
    ).first()
    return pv.rules if pv and pv.rules else DEFAULT_RULES


def _persist_hypotheses(session: Session, alert_id: uuid.UUID, scope: AlertScope) -> None:
    for h in scope.hypotheses:
        th = TypologyHypothesis(
            alert_id=alert_id,
            typology=h.typology.value,
            likelihood=h.likelihood,
            rationale=h.rationale,
        )
        session.add(th)
        session.flush()
        # The citation join — every claim bound to the transaction that proves it.
        for cite in h.evidence:
            session.add(
                AlertEvidence(
                    typology_hypothesis_id=th.id,
                    transaction_id=uuid.UUID(cite.transaction_id),
                    locator=cite.locator,
                    quote=cite.quote,
                )
            )


def resolve_alert(session: Session, alert_id: uuid.UUID) -> ResolveResult:
    ctx = AlertContext.load(session, alert_id)
    scope, facts = build_alert_scope(ctx)
    rules = _load_rules(session, ctx.tenant_id)
    decision = evaluate_routing(rules, facts)

    adapters = build_adapters(ctx.settings)
    refs: dict = {}

    alert: Alert = ctx.alert
    _persist_hypotheses(session, alert.id, scope)

    # Every disposition stores its full reasoning trace — the exam artifact.
    session.add(
        DispositionRecord(
            alert_id=alert.id,
            decision=scope.disposition.value,
            rationale_md=scope.rationale_md,
            decided_by="agent",
            reasoning_trace=scope.reasoning_trace(),
        )
    )

    if scope.decision_action == DecisionAction.CLEAR:
        # Auto-clear: logged with a full cited rationale. Never a silent drop.
        refs["clear"] = adapters.casemgmt.log_disposition(alert.external_alert_id, "clear")
        outcome = AlertStatus.CLEARED.value
    elif scope.decision_action == DecisionAction.ESCALATE:
        if scope.sar is not None:
            sar = scope.sar
            session.add(
                SARDraft(
                    alert_id=alert.id,
                    narrative_md=sar.narrative_md,
                    five_w=sar.five_w,
                    total_amount=sar.total_amount,
                    period_start=_date(sar.period_start),
                    period_end=_date(sar.period_end),
                    evidence_index=sar.evidence_index,
                    status="draft",
                )
            )
            refs["sar"] = adapters.casemgmt.export_sar_draft(alert.external_alert_id)
        session.add(
            ReviewTask(alert_id=alert.id, kind="escalation", status=ReviewStatus.OPEN.value, reason=decision.reason)
        )
        refs["notify"] = adapters.casemgmt.open_case(alert.external_alert_id)
        outcome = AlertStatus.ESCALATED.value
    else:  # RFI
        session.add(ReviewTask(alert_id=alert.id, kind="rfi", status=ReviewStatus.OPEN.value, reason=decision.reason))
        refs["rfi"] = adapters.casemgmt.open_case(alert.external_alert_id)
        outcome = AlertStatus.RFI.value

    scope.escalation_reason = decision.reason if decision.route == "hitl" else None
    alert.status = outcome
    alert.disposition = scope.disposition.value
    alert.confidence = scope.confidence
    alert.escalation_reason = scope.escalation_reason
    alert.scope_json = scope.model_dump_json_safe()

    write_audit(
        session,
        tenant_id=ctx.tenant_id,
        case_id=alert.id,
        action=f"alert.{decision.route}",
        actor="agent",
        after={
            "alert": alert.external_alert_id,
            "disposition": scope.disposition.value,
            "typologies": [h.typology.value for h in scope.evidenced_hypotheses],
            "confidence": scope.confidence,
            "route": decision.route,
            "rule": decision.matched_rule_id,
            "outcome": outcome,
            "refs": refs,
        },
        meta={"reason": decision.reason, "rule_id": alert.rule_id},
    )
    session.flush()
    return ResolveResult(
        scope=scope,
        route=decision.route,
        matched_rule_id=decision.matched_rule_id,
        reason=decision.reason,
        outcome=outcome,
        refs=refs,
    )


def _date(iso: str | None):
    import datetime as _dt

    if not iso:
        return None
    try:
        return _dt.date.fromisoformat(iso[:10])
    except ValueError:
        return None
