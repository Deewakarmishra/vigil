"""Adapter protocols + a small info record for the connector inspector.

The agent never branches on connector implementation — it calls these protocols.
Mock implementations close the loop deterministically (no outbound calls); live
implementations wire real provider APIs behind the identical interface. The
case-management adapter deliberately exposes no ``file_sar`` — the agent's role
literally cannot file. An officer files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdapterInfo:
    provider: str
    kind: str  # tm | ledger | casemgmt
    mode: str  # mock | live
    note: str


class TMAdapter(Protocol):
    """Transaction-monitoring engine (Actimize / Unit21 / in-house)."""

    info: AdapterInfo

    def fetch_alert(self, external_alert_id: str) -> str: ...


class LedgerAdapter(Protocol):
    """Core-banking / ledger: transactions + accounts."""

    info: AdapterInfo

    def fetch_transactions(self, customer_ref: str) -> str: ...


class CaseMgmtAdapter(Protocol):
    """Case system + FinCEN BSA E-Filing. Drafts only — the officer files."""

    info: AdapterInfo

    def log_disposition(self, external_alert_id: str, decision: str) -> str: ...

    def open_case(self, external_alert_id: str) -> str: ...

    def export_sar_draft(self, external_alert_id: str) -> str: ...
