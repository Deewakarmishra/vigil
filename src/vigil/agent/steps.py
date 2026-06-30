"""Agent steps: enrich → retrieve/hypothesize → cite → reflect → dispose → draft_sar.

Each step is a pure function over the AlertContext, returning a typed fragment of
the AlertScope. The judging is deterministic and inspectable; the guardrails are
enforced in ``step_reflect`` (a typology claim survives only with a bound
citation) and in the disposition order (a clear can never precede the typology
check — recall is protected first).
"""

from __future__ import annotations

from vigil.agent.context import AlertContext
from vigil.contracts.alert_scope import Enrichment, TypologyClaim
from vigil.detection import assess_baseline, detect_typologies
from vigil.models.enums import DecisionAction, Disposition

# ---- step 1: enrich ---------------------------------------------------------


def step_enrich(ctx: AlertContext) -> Enrichment:
    cust = ctx.customer
    observed, expected_max, explained = assess_baseline(ctx.transactions, ctx.baseline)
    counterparties = {t.counterparty_name for t in ctx.transactions if t.counterparty_name}
    return Enrichment(
        customer_ref=(cust.external_id if cust else ""),
        entity_type=(cust.entity_type if cust else ""),
        risk_rating=(cust.risk_rating if cust else "low"),
        pep=(ctx.kyc.pep if ctx.kyc else False),
        has_kyc=ctx.kyc is not None,
        counterparty_count=len(counterparties),
        prior_alert_count=0,
        observed_amount=observed,
        expected_max_amount=expected_max,
        baseline_explained=explained,
    )


# ---- steps 2+3: retrieve typology library + hypothesize + cite --------------


def step_hypothesize(ctx: AlertContext) -> list[TypologyClaim]:
    """Form typology hypotheses, each already bound to its transactions."""

    return detect_typologies(ctx.transactions)


# ---- step 4: reflect — drop any hypothesis without a transaction behind it ---


def step_reflect(hyps: list[TypologyClaim]) -> list[TypologyClaim]:
    return [h for h in hyps if h.is_evidenced]


# ---- step 5: dispose --------------------------------------------------------


def decide_disposition(
    *,
    evidenced: bool,
    has_kyc: bool,
    baseline_explained: bool,
) -> tuple[Disposition, DecisionAction]:
    """Recall is protected: the typology check precedes any clear.

    A clear is only ever reached when there is no evidenced typology *and* the
    customer's own baseline explains the activity — never silently.
    """

    if evidenced:
        return Disposition.ESCALATE, DecisionAction.ESCALATE
    if not has_kyc:
        return Disposition.NEED_INFO, DecisionAction.RFI
    if baseline_explained:
        return Disposition.CLEAR, DecisionAction.CLEAR
    # Unexplained + no typology evidence: do not clear — escalate for a human look.
    return Disposition.ESCALATE, DecisionAction.ESCALATE


def confidence_for(disposition: Disposition, top_likelihood: float, *, has_kyc: bool) -> float:
    if disposition == Disposition.ESCALATE:
        return round(max(top_likelihood, 0.7), 2)
    if disposition == Disposition.CLEAR:
        return 0.9
    if not has_kyc:
        return 0.4  # cannot assess without KYC
    return 0.55
