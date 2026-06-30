"""Agent steps: enrich → retrieve/hypothesize → cite → reflect → dispose → draft_sar.

Each step is a pure function over the AlertContext, returning a typed fragment of
the AlertScope. The judging is deterministic and inspectable; the guardrails are
enforced in ``step_reflect`` (a typology claim survives only with a bound
citation) and in the disposition order (a clear can never precede the typology
check — recall is protected first). Disposition is now driven by a continuous
``suspicion_score`` against a tunable ``clear_threshold``, so the FP/FN trade-off
is a real, swept curve rather than a fixed point.
"""

from __future__ import annotations

from collections.abc import Sequence

from vigil.agent.context import AlertContext
from vigil.contracts.alert_scope import Enrichment, TypologyClaim
from vigil.detection import assess_baseline, detect_typologies
from vigil.models.enums import DecisionAction, Disposition
from vigil.scoring import baseline_deviation, suspicion_score
from vigil.typology_library import get_library

# ---- step 1: enrich ---------------------------------------------------------


def step_enrich(ctx: AlertContext, claims: Sequence[TypologyClaim]) -> Enrichment:
    cust = ctx.customer
    tol = ctx.settings.baseline_tolerance
    observed, expected_max, explained = assess_baseline(ctx.transactions, ctx.baseline, tolerance=tol)
    deviation = baseline_deviation(observed, expected_max, tolerance=tol)
    risk = cust.risk_rating if cust else "low"
    pep = ctx.kyc.pep if ctx.kyc else False
    score = suspicion_score(claims, deviation, risk_rating=risk, pep=pep)
    counterparties = {t.counterparty_name for t in ctx.transactions if t.counterparty_name}
    return Enrichment(
        customer_ref=(cust.external_id if cust else ""),
        entity_type=(cust.entity_type if cust else ""),
        risk_rating=risk,
        pep=pep,
        has_kyc=ctx.kyc is not None,
        counterparty_count=len(counterparties),
        prior_alert_count=ctx.prior_alert_count,
        observed_amount=observed,
        expected_max_amount=expected_max,
        baseline_explained=explained,
        baseline_deviation=deviation,
        suspicion_score=score,
    )


# ---- steps 2+3: retrieve typology library + hypothesize + cite --------------


def step_hypothesize(ctx: AlertContext) -> list[TypologyClaim]:
    """Form typology hypotheses, each already bound to its transactions, using the
    versioned typology library scoped to the alert date."""

    return detect_typologies(ctx.transactions, get_library(), as_of=ctx.as_of)


# ---- step 4: reflect — drop any hypothesis without a transaction behind it ---


def step_reflect(hyps: list[TypologyClaim]) -> list[TypologyClaim]:
    return [h for h in hyps if h.is_evidenced]


# ---- step 5: dispose --------------------------------------------------------


def decide_disposition(
    *,
    evidenced: bool,
    has_kyc: bool,
    baseline_explained: bool,
    suspicion_score: float = 0.0,
    clear_threshold: float = 0.30,
) -> tuple[Disposition, DecisionAction]:
    """Recall is protected: the typology check precedes any clear.

    A clear is only ever reached when there is no evidenced typology, the customer's
    own baseline explains the activity, *and* the continuous suspicion score is at or
    below the tunable clear threshold — never silently, and never above the operating
    point an officer has signed off on.
    """

    if evidenced:
        return Disposition.ESCALATE, DecisionAction.ESCALATE
    if not has_kyc:
        return Disposition.NEED_INFO, DecisionAction.RFI
    if baseline_explained and suspicion_score <= clear_threshold:
        return Disposition.CLEAR, DecisionAction.CLEAR
    # Unexplained, or above the clear threshold: do not clear — escalate for a human.
    return Disposition.ESCALATE, DecisionAction.ESCALATE


def confidence_for(disposition: Disposition, suspicion_score: float, *, has_kyc: bool) -> float:
    """Confidence is derived from the suspicion score, not a fixed constant.

    On an escalation, confidence tracks the score (how strongly the activity reads
    as suspicious); on a clear, it is the inverse (how strongly it reads as benign).
    Both are floored so a genuine disposition never trips the low-confidence route.
    """

    if disposition == Disposition.ESCALATE:
        return round(max(0.6, min(0.99, suspicion_score)), 2)
    if disposition == Disposition.CLEAR:
        return round(max(0.6, 1.0 - suspicion_score), 2)
    if not has_kyc:
        return 0.4  # cannot assess without KYC
    return 0.55
