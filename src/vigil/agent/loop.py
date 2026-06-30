"""The agent loop: walk the steps, assemble an AlertScope. Pure (reads only).

enrich → hypothesize (detect + cite) → reflect (drop uncited claims) → dispose
(clear / escalate / RFI) → draft SAR for escalations. The agent proposes; the
officer disposes and files.
"""

from __future__ import annotations

from vigil.agent.context import AlertContext
from vigil.agent.steps import (
    confidence_for,
    decide_disposition,
    step_enrich,
    step_hypothesize,
    step_reflect,
)
from vigil.contracts.alert_scope import AlertScope
from vigil.models.enums import Disposition
from vigil.sar import draft_sar


def _rationale(scope: AlertScope) -> str:
    enr = scope.enrichment
    if scope.disposition == Disposition.CLEAR:
        return (
            f"Cleared as a false positive: no evidenced typology, and observed activity "
            f"(${enr.observed_amount:,.0f}) is within the customer's established baseline "
            f"(${enr.expected_max_amount:,.0f}). {scope.alert_reason} explained by KYC profile. "
            f"Rationale stored for examination."
        )
    if scope.disposition == Disposition.NEED_INFO:
        return (
            "Request for information: no KYC profile on file, so the activity cannot be assessed "
            "against an expected baseline. Routed to staff to obtain KYC before disposition."
        )
    typ = ", ".join(sorted({h.typology.value for h in scope.evidenced_hypotheses})) or "unexplained activity"
    return (
        f"Escalated for officer review: {typ} detected with cited transaction evidence; "
        f"activity is not explained by the customer's baseline. SAR draft prepared."
    )


def build_alert_scope(ctx: AlertContext) -> tuple[AlertScope, dict]:
    """Run the agent loop and return ``(scope, routing_facts)``."""

    enrichment = step_enrich(ctx)
    hyps = step_reflect(step_hypothesize(ctx))

    scope = AlertScope(
        alert_id=str(ctx.alert.id),
        external_alert_id=ctx.alert.external_alert_id,
        rule_id=ctx.alert.rule_id,
        alert_reason=ctx.alert.alert_reason,
        enrichment=enrichment,
        hypotheses=hyps,
    )

    disposition, action = decide_disposition(
        evidenced=bool(scope.evidenced_hypotheses),
        has_kyc=enrichment.has_kyc,
        baseline_explained=enrichment.baseline_explained,
    )
    scope.disposition = disposition
    scope.decision_action = action
    scope.confidence = confidence_for(disposition, scope.top_likelihood, has_kyc=enrichment.has_kyc)
    scope.rationale_md = _rationale(scope)

    if disposition == Disposition.ESCALATE and scope.evidenced_hypotheses:
        scope.sar = draft_sar(scope)

    return scope, scope.routing_facts()
