"""Mock adapters: deterministic, no outbound calls. The demo path."""

from __future__ import annotations

import hashlib

from vigil.adapters.base import AdapterInfo


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


class MockTM:
    info = AdapterInfo("tm", "tm", "mock", "Deterministic mock TM engine (Actimize/Unit21 shape).")

    def fetch_alert(self, external_alert_id: str) -> str:
        return _ref("ALERT", external_alert_id)


class MockLedger:
    info = AdapterInfo("ledger", "ledger", "mock", "Synthetic transaction histories per customer.")

    def fetch_transactions(self, customer_ref: str) -> str:
        return _ref("TXNS", customer_ref)


class MockCaseMgmt:
    info = AdapterInfo("casemgmt", "casemgmt", "mock", "Mock case store + SAR draft export (no real filing).")

    def log_disposition(self, external_alert_id: str, decision: str) -> str:
        return _ref("DISP", external_alert_id, decision)

    def open_case(self, external_alert_id: str) -> str:
        return _ref("CASE", external_alert_id)

    def export_sar_draft(self, external_alert_id: str) -> str:
        return _ref("SAR", external_alert_id)
