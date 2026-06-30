"""Integration test: end-to-end alert triage + eval against a real Postgres DB."""

import pytest
from sqlalchemy import select

from vigil.agent.runner import resolve_alert
from vigil.config import get_settings
from vigil.eval.harness import run_eval
from vigil.models.aml import Alert
from vigil.models.enums import AlertStatus
from vigil.models.tenant import Tenant


@pytest.mark.integration
def test_pipeline_triages_and_routes(seeded_session):
    s = seeded_session
    settings = get_settings()
    tenant = s.scalars(select(Tenant).where(Tenant.slug == settings.demo_brand_slug)).first()
    assert tenant is not None

    alerts = list(s.scalars(select(Alert).where(Alert.tenant_id == tenant.id, Alert.status == "new")))
    assert alerts, "demo alerts should be seeded"

    outcomes = []
    for alert in alerts:
        result = resolve_alert(s, alert.id)
        outcomes.append(result.outcome)
    s.commit()

    # The demo spans cleared, escalated, and RFI outcomes.
    assert AlertStatus.CLEARED.value in outcomes
    assert AlertStatus.ESCALATED.value in outcomes
    assert AlertStatus.RFI.value in outcomes


@pytest.mark.integration
def test_eval_metrics_meet_bar(seeded_session):
    s = seeded_session
    settings = get_settings()
    metrics, records = run_eval(s, settings.demo_brand_slug)

    assert metrics["total_alerts"] == 9
    # Zero-tolerance recall gate — the moral + regulatory core.
    assert metrics["false_negatives"] == 0
    assert metrics["disposition_accuracy"] == 1.0
    assert metrics["route_accuracy"] == 1.0
    assert metrics["typology_recall"] == 1.0
    assert metrics["citation_precision"] == 1.0
    assert metrics["sar_completeness"] == 1.0
    # All planted false positives auto-cleared.
    assert metrics["fp_reduction"] == 1.0
