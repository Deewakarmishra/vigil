"""JSON-stable string enums shared across the API + DB + agent layers."""

from __future__ import annotations

from enum import Enum


class EntityType(str, Enum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class RiskRating(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TxnDirection(str, Enum):
    CREDIT = "credit"  # money in
    DEBIT = "debit"  # money out


class Typology(str, Enum):
    STRUCTURING = "structuring"  # deposits just under the CTR threshold
    LAYERING = "layering"  # rapid in-then-out to obscure origin
    RAPID_MOVEMENT = "rapid_movement"
    MULE = "mule"  # many unrelated inbounds funneled out
    SANCTIONS_NAME_MATCH = "sanctions_name_match"  # screening hit


class Disposition(str, Enum):
    CLEAR = "clear"  # false positive — auto-cleared with a cited rationale
    ESCALATE = "escalate"  # suspicious — officer reviews + files
    NEED_INFO = "need_info"  # missing KYC / data — request-for-information


class DecisionAction(str, Enum):
    CLEAR = "clear"
    ESCALATE = "escalate"
    RFI = "rfi"


class AlertStatus(str, Enum):
    NEW = "new"
    CLEARED = "cleared"
    ESCALATED = "escalated"
    RFI = "rfi"
    FILED = "filed"  # officer filed the SAR (post-HITL)


class SARStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    FILED = "filed"


class ReviewStatus(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class Actor(str, Enum):
    AGENT = "agent"
    OFFICER = "officer"
