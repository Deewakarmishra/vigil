"""Agent subsystem: a custom, inspectable loop (no framework)."""

from vigil.agent.context import AlertContext
from vigil.agent.loop import build_alert_scope
from vigil.agent.runner import resolve_alert

__all__ = ["AlertContext", "build_alert_scope", "resolve_alert"]
