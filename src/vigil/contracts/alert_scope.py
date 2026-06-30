"""`AlertScope` — the single typed artifact the agent produces per alert.

The loop assembles it; the policy engine routes on it; the console renders it as
the Alert-Disposition view; the eval harness scores it. The guardrails live in the
type: a typology hypothesis survives ``reflect`` only if it has at least one bound
citation (claim ↔ transaction), and the disposition is a recommendation — a
compliance officer disposes and files, never the agent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from vigil.models.enums import DecisionAction, Disposition, Typology


class TxnCitation(BaseModel):
    transaction_id: str
    locator: str
    quote: str
    amount: float = 0.0
    occurred_on: str | None = None


class TypologyClaim(BaseModel):
    typology: Typology
    likelihood: float = 0.0
    rationale: str = ""
    evidence: list[TxnCitation] = Field(default_factory=list)

    @property
    def is_evidenced(self) -> bool:
        return bool(self.evidence)


class Enrichment(BaseModel):
    customer_ref: str = ""
    entity_type: str = ""
    risk_rating: str = "low"
    pep: bool = False
    has_kyc: bool = False
    counterparty_count: int = 0
    prior_alert_count: int = 0
    observed_amount: float = 0.0
    expected_max_amount: float = 0.0
    baseline_explained: bool = False


class SARNarrative(BaseModel):
    narrative_md: str = ""
    five_w: dict = Field(default_factory=dict)
    total_amount: float = 0.0
    period_start: str | None = None
    period_end: str | None = None
    evidence_index: list[dict] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        required = ("who", "what", "when", "where", "why")
        return all(self.five_w.get(k) for k in required)


class AlertScope(BaseModel):
    alert_id: str
    external_alert_id: str = ""
    rule_id: str = ""
    alert_reason: str = ""
    enrichment: Enrichment = Field(default_factory=Enrichment)
    hypotheses: list[TypologyClaim] = Field(default_factory=list)
    disposition: Disposition = Disposition.NEED_INFO
    decision_action: DecisionAction = DecisionAction.RFI
    confidence: float = 0.0
    rationale_md: str = ""
    sar: SARNarrative | None = None
    escalation_reason: str | None = None

    # ---- derived helpers ----

    @property
    def evidenced_hypotheses(self) -> list[TypologyClaim]:
        return [h for h in self.hypotheses if h.is_evidenced]

    @property
    def top_likelihood(self) -> float:
        return max((h.likelihood for h in self.evidenced_hypotheses), default=0.0)

    def reasoning_trace(self) -> dict:
        """The full, examiner-readable trace stored on the disposition."""

        return {
            "enrichment": self.enrichment.model_dump(mode="json"),
            "hypotheses": [h.model_dump(mode="json") for h in self.hypotheses],
            "disposition": self.disposition.value,
            "confidence": self.confidence,
        }

    def model_dump_json_safe(self) -> dict:
        return self.model_dump(mode="json")

    def routing_facts(self) -> dict:
        """Flat fact dict the (generic) policy engine matches rules against."""

        return {
            "action": self.decision_action.value,
            "disposition": self.disposition.value,
            "has_kyc": self.enrichment.has_kyc,
            "typology_likely": bool(self.evidenced_hypotheses),
            "baseline_explained": self.enrichment.baseline_explained,
            "confidence": self.confidence,
        }
