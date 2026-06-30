"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from vigil.models.aml import (
    Alert,
    AlertEvidence,
    Counterparty,
    Customer,
    CustomerBaseline,
    DispositionRecord,
    KYCProfile,
    SARDraft,
    Transaction,
    TypologyHypothesis,
)
from vigil.models.audit import AuditLog
from vigil.models.connector_account import ConnectorAccount
from vigil.models.enums import (
    Actor,
    AlertStatus,
    DecisionAction,
    Disposition,
    EntityType,
    ReviewStatus,
    RiskRating,
    SARStatus,
    TxnDirection,
    Typology,
)
from vigil.models.evaluation import EvalCase, EvalRun
from vigil.models.policy import PolicyDefinition, PolicyVersion
from vigil.models.review import ReviewAction, ReviewTask
from vigil.models.tenant import Tenant
from vigil.models.user import User

__all__ = [
    "Alert",
    "AlertEvidence",
    "AuditLog",
    "ConnectorAccount",
    "Counterparty",
    "Customer",
    "CustomerBaseline",
    "DispositionRecord",
    "KYCProfile",
    "SARDraft",
    "Transaction",
    "TypologyHypothesis",
    "PolicyDefinition",
    "PolicyVersion",
    "ReviewAction",
    "ReviewTask",
    "EvalRun",
    "EvalCase",
    "Tenant",
    "User",
    # enums
    "Actor",
    "AlertStatus",
    "DecisionAction",
    "Disposition",
    "EntityType",
    "ReviewStatus",
    "RiskRating",
    "SARStatus",
    "Typology",
    "TxnDirection",
]
