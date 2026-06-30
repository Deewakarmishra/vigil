"""Adapter registry: assemble the right bundle for the configured mode."""

from __future__ import annotations

from dataclasses import dataclass

from vigil.adapters.base import AdapterInfo, CaseMgmtAdapter, LedgerAdapter, TMAdapter
from vigil.adapters.live import LiveCaseMgmt, LiveLedger, LiveTM
from vigil.adapters.mock import MockCaseMgmt, MockLedger, MockTM
from vigil.config import Settings, get_settings


@dataclass(frozen=True)
class AdapterBundle:
    tm: TMAdapter
    ledger: LedgerAdapter
    casemgmt: CaseMgmtAdapter


def build_adapters(settings: Settings | None = None) -> AdapterBundle:
    s = settings or get_settings()
    if s.is_mock:
        return AdapterBundle(MockTM(), MockLedger(), MockCaseMgmt())
    return AdapterBundle(LiveTM(), LiveLedger(), LiveCaseMgmt())


def list_adapter_info(settings: Settings | None = None) -> list[AdapterInfo]:
    b = build_adapters(settings)
    return [b.tm.info, b.ledger.info, b.casemgmt.info]
