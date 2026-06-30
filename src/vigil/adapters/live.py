"""Live adapter shells.

These validate configuration and then raise ``NotImplementedError`` on the actual
call — explicit and honest, never a silent no-op. Real provider wiring (TM engine
exports, core-banking ledger, case system + FinCEN BSA E-Filing draft export)
lands per engagement behind the identical protocol the mocks satisfy. Filing
itself is always an officer action — no adapter files autonomously.
"""

from __future__ import annotations

from vigil.adapters.base import AdapterInfo

_MSG = "live connector wiring lands per engagement; run with CONNECTOR_MODE=mock for the demo"


class LiveTM:
    info = AdapterInfo("tm", "tm", "live", "Actimize / Unit21 / in-house alert export — per engagement.")

    def fetch_alert(self, external_alert_id: str) -> str:
        raise NotImplementedError(_MSG)


class LiveLedger:
    info = AdapterInfo("ledger", "ledger", "live", "Core-banking / ledger API — per engagement.")

    def fetch_transactions(self, customer_ref: str) -> str:
        raise NotImplementedError(_MSG)


class LiveCaseMgmt:
    info = AdapterInfo("casemgmt", "casemgmt", "live", "Case API + FinCEN BSA E-Filing draft export — per engagement.")

    def log_disposition(self, external_alert_id: str, decision: str) -> str:
        raise NotImplementedError(_MSG)

    def open_case(self, external_alert_id: str) -> str:
        raise NotImplementedError(_MSG)

    def export_sar_draft(self, external_alert_id: str) -> str:
        raise NotImplementedError(_MSG)
