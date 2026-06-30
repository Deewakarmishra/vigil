"""Unit tests for the AlertScope contract, the disposition guardrail, and SAR drafting."""

import pytest

from vigil.agent.steps import confidence_for, decide_disposition
from vigil.contracts.alert_scope import AlertScope, TxnCitation, TypologyClaim
from vigil.models.enums import DecisionAction, Disposition, Typology
from vigil.sar import draft_sar


def _claim(evidenced: bool = True) -> TypologyClaim:
    ev = (
        [
            TxnCitation(
                transaction_id="t1",
                locator="Txn T1",
                quote="+$9,400 cash on 2026-06-20",
                amount=9400,
                occurred_on="2026-06-20",
            )
        ]
        if evidenced
        else []
    )
    return TypologyClaim(typology=Typology.STRUCTURING, likelihood=0.84, rationale="five sub-CTR deposits", evidence=ev)


@pytest.mark.unit
def test_evidenced_hypotheses_filters_uncited_claims():
    scope = AlertScope(alert_id="a", hypotheses=[_claim(True), _claim(False)])
    assert len(scope.evidenced_hypotheses) == 1
    assert scope.top_likelihood == 0.84


@pytest.mark.unit
def test_decide_disposition_protects_recall():
    # Evidenced typology always escalates — even if the baseline would explain it.
    assert decide_disposition(evidenced=True, has_kyc=True, baseline_explained=True) == (
        Disposition.ESCALATE,
        DecisionAction.ESCALATE,
    )
    # No typology + no KYC → RFI (cannot assess).
    assert decide_disposition(evidenced=False, has_kyc=False, baseline_explained=False) == (
        Disposition.NEED_INFO,
        DecisionAction.RFI,
    )
    # No typology + within baseline → clear.
    assert decide_disposition(evidenced=False, has_kyc=True, baseline_explained=True) == (
        Disposition.CLEAR,
        DecisionAction.CLEAR,
    )
    # No typology, unexplained, has KYC → never clear; escalate for a human look.
    assert decide_disposition(evidenced=False, has_kyc=True, baseline_explained=False) == (
        Disposition.ESCALATE,
        DecisionAction.ESCALATE,
    )


@pytest.mark.unit
def test_confidence_bands():
    assert confidence_for(Disposition.CLEAR, 0.0, has_kyc=True) == 0.9
    assert confidence_for(Disposition.ESCALATE, 0.84, has_kyc=True) == 0.84
    assert confidence_for(Disposition.NEED_INFO, 0.0, has_kyc=False) == 0.4


@pytest.mark.unit
def test_sar_draft_has_all_five_w_and_evidence_index():
    scope = AlertScope(alert_id="a", external_alert_id="TM-1", hypotheses=[_claim(True)])
    scope.disposition = Disposition.ESCALATE
    sar = draft_sar(scope)
    assert sar.is_complete  # all 5W present
    assert sar.total_amount == 9400
    assert sar.evidence_index and sar.evidence_index[0]["transactions"] == ["Txn T1"]
