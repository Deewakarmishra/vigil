"""SAR narrative drafting — a regulator-readable 5W narrative with an evidence index.

Pure and deterministic: it assembles the narrative from the evidenced typology
hypotheses and their bound transaction citations. Every sentence maps to the
transactions behind it via ``evidence_index``. Never auto-filed — an officer files.
"""

from __future__ import annotations

from vigil.contracts.alert_scope import AlertScope, SARNarrative, TypologyClaim


def _period(scope: AlertScope) -> tuple[str | None, str | None]:
    dates = [c.occurred_on for h in scope.evidenced_hypotheses for c in h.evidence if c.occurred_on]
    if not dates:
        return None, None
    return min(dates), max(dates)


def _total(scope: AlertScope) -> float:
    seen: dict[str, float] = {}
    for h in scope.evidenced_hypotheses:
        for c in h.evidence:
            seen[c.transaction_id] = c.amount
    return round(sum(seen.values()), 2)


def draft_sar(scope: AlertScope) -> SARNarrative:
    enr = scope.enrichment
    hyps: list[TypologyClaim] = scope.evidenced_hypotheses
    typ_names = ", ".join(sorted({h.typology.value for h in hyps})) or "suspicious activity"
    start, end = _period(scope)
    total = _total(scope)

    five_w = {
        "who": f"{enr.customer_ref} ({enr.entity_type}, risk={enr.risk_rating}" + (", PEP" if enr.pep else "") + ")",
        "what": f"{typ_names}; aggregate ${total:,.0f} across {sum(len(h.evidence) for h in hyps)} transactions",
        "when": f"{start} to {end}" if start else "within the alert lookback window",
        "where": f"{enr.counterparty_count} counterparties; channels per cited transactions",
        "why": "; ".join(h.rationale for h in hyps),
    }

    lines = [
        f"## Suspicious Activity Report (DRAFT) — alert {scope.external_alert_id}",
        "",
        f"**Subject (Who):** {five_w['who']}",
        f"**Activity (What):** {five_w['what']}",
        f"**Period (When):** {five_w['when']}",
        f"**Channels / counterparties (Where):** {five_w['where']}",
        "",
        "**Basis for suspicion (Why):**",
    ]
    evidence_index: list[dict] = []
    for h in hyps:
        lines.append(f"- *{h.typology.value}* (likelihood {h.likelihood:.2f}): {h.rationale}")
        for c in h.evidence:
            lines.append(f"    - {c.locator}: {c.quote}")
        evidence_index.append({"claim": h.typology.value, "transactions": [c.locator for c in h.evidence]})
    lines += [
        "",
        "_This draft was prepared by the Vigil agent for compliance-officer review. "
        "No SAR is filed and no account is restricted without officer disposition._",
    ]

    return SARNarrative(
        narrative_md="\n".join(lines),
        five_w=five_w,
        total_amount=total,
        period_start=start,
        period_end=end,
        evidence_index=evidence_index,
    )
