"""Vigil over the Model Context Protocol — read-only triage tools for an agent host.

This exposes the triage engine as MCP tools so another agent (or an MCP-aware IDE)
can pull an alert's full reasoning scope, inspect a customer's enrichment, search
the transaction lookback, or fetch a SAR draft — without the caller touching the
database or re-implementing the loop. It is deliberately **read-only**: nothing here
files a SAR, restricts an account, or mutates a disposition. Filing stays an officer
action in the console.

Optional — requires the ``[mcp]`` extra (``pip install -e '.[mcp]'``). Nothing in
the core demo / eval / console path imports this module, so the base install,
tests, and CI never depend on the MCP package.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from vigil.agent.context import AlertContext
from vigil.agent.loop import build_alert_scope
from vigil.config import get_settings
from vigil.db.session import session_scope
from vigil.models.aml import Alert, Customer, KYCProfile, SARDraft, Transaction
from vigil.models.tenant import Tenant

mcp = FastMCP("vigil")


def _tenant_id(session) -> Any:
    slug = get_settings().demo_brand_slug
    tenant = session.scalars(select(Tenant).where(Tenant.slug == slug)).first()
    return tenant.id if tenant else None


def _find_alert(session, external_alert_id: str) -> Alert | None:
    return session.scalars(select(Alert).where(Alert.external_alert_id == external_alert_id)).first()


@mcp.tool()
def list_alerts() -> list[dict]:
    """List every alert with its current disposition, route, and suspicion score."""

    with session_scope() as s:
        tid = _tenant_id(s)
        if tid is None:
            return []
        rows = []
        for a in s.scalars(select(Alert).where(Alert.tenant_id == tid).order_by(Alert.external_alert_id)):
            enr = (a.scope_json or {}).get("enrichment", {})
            rows.append(
                {
                    "external_alert_id": a.external_alert_id,
                    "rule_id": a.rule_id,
                    "reason": a.alert_reason,
                    "status": a.status,
                    "disposition": a.disposition,
                    "confidence": a.confidence,
                    "suspicion_score": enr.get("suspicion_score"),
                }
            )
        return rows


@mcp.tool()
def get_alert(external_alert_id: str) -> dict:
    """Return the full AlertScope (enrichment, cited hypotheses, disposition, SAR) for one alert.

    Recomputed from the agent loop so the trace is always consistent with the
    current typology library — never a stale snapshot.
    """

    with session_scope() as s:
        alert = _find_alert(s, external_alert_id)
        if alert is None:
            return {"error": f"alert {external_alert_id} not found"}
        scope, facts = build_alert_scope(AlertContext.load(s, alert.id))
        out = scope.model_dump_json_safe()
        out["routing_facts"] = facts
        return out


@mcp.tool()
def enrich_customer(external_id: str) -> dict:
    """Return a customer's KYC + risk profile and their alert count."""

    with session_scope() as s:
        tid = _tenant_id(s)
        cust = s.scalars(select(Customer).where(Customer.tenant_id == tid, Customer.external_id == external_id)).first()
        if cust is None:
            return {"error": f"customer {external_id} not found"}
        kyc = s.scalars(select(KYCProfile).where(KYCProfile.customer_id == cust.id)).first()
        alert_count = sum(1 for _ in s.scalars(select(Alert).where(Alert.customer_id == cust.id)))
        return {
            "external_id": cust.external_id,
            "name": cust.name,
            "entity_type": cust.entity_type,
            "risk_rating": cust.risk_rating,
            "has_kyc": kyc is not None,
            "occupation": kyc.occupation if kyc else None,
            "pep": kyc.pep if kyc else None,
            "expected_activity": kyc.expected_activity if kyc else None,
            "alert_count": alert_count,
        }


@mcp.tool()
def search_transactions(external_id: str, min_amount: float = 0.0, direction: str | None = None) -> list[dict]:
    """Search a customer's transactions, optionally filtered by amount and direction."""

    with session_scope() as s:
        tid = _tenant_id(s)
        cust = s.scalars(select(Customer).where(Customer.tenant_id == tid, Customer.external_id == external_id)).first()
        if cust is None:
            return []
        q = select(Transaction).where(Transaction.customer_id == cust.id).order_by(Transaction.occurred_on)
        rows = []
        for t in s.scalars(q):
            if float(t.amount) < min_amount:
                continue
            if direction and t.direction != direction:
                continue
            rows.append(
                {
                    "external_txn_id": t.external_txn_id,
                    "amount": float(t.amount),
                    "direction": t.direction,
                    "channel": t.channel,
                    "counterparty": t.counterparty_name,
                    "occurred_on": t.occurred_on.isoformat() if t.occurred_on else None,
                }
            )
        return rows


@mcp.tool()
def get_sar_draft(external_alert_id: str) -> dict:
    """Return the drafted SAR narrative + evidence index for an escalated alert."""

    with session_scope() as s:
        alert = _find_alert(s, external_alert_id)
        if alert is None:
            return {"error": f"alert {external_alert_id} not found"}
        sar = s.scalars(select(SARDraft).where(SARDraft.alert_id == alert.id)).first()
        if sar is None:
            return {"error": f"no SAR draft for {external_alert_id} (only escalations carry one)"}
        return {
            "external_alert_id": external_alert_id,
            "narrative_md": sar.narrative_md,
            "five_w": sar.five_w,
            "total_amount": float(sar.total_amount),
            "evidence_index": sar.evidence_index,
            "status": sar.status,
        }


if __name__ == "__main__":
    mcp.run()
