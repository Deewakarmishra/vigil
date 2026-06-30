"""Evaluate routing rules against a flat fact dict. First match wins.

This engine is domain-agnostic: a rule's ``when`` block is matched against a
``facts`` dict the runner assembles from the scope. Three operators are encoded
in the key suffix:

  - ``<key>``            exact equality (``facts[key] == value``)
  - ``<key>_below``      ``facts[key] < value``
  - ``<key>_above``      ``facts[key] > value``

An empty ``when`` always matches — use it for the default rule, listed last.
For Vigil the facts are: action, severity, trade, safety_flag, after_hours,
tech_available, confidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    route: str  # auto | hitl
    matched_rule_id: str
    reason: str


def _matches(when: dict, facts: dict) -> bool:
    for key, expected in when.items():
        if key.endswith("_below"):
            base = key[: -len("_below")]
            if not (float(facts.get(base, math.inf)) < float(expected)):
                return False
        elif key.endswith("_above"):
            base = key[: -len("_above")]
            if not (float(facts.get(base, -math.inf)) > float(expected)):
                return False
        else:
            if facts.get(key) != expected:
                return False
    return True


def evaluate_routing(rules: list[dict], facts: dict) -> PolicyDecision:
    for rule in rules:
        if _matches(rule.get("when", {}), facts):
            return PolicyDecision(
                route=rule["route"], matched_rule_id=rule["id"], reason=rule.get("reason", rule["id"])
            )
    # No rule matched (no default present): fail safe to human review.
    return PolicyDecision(route="hitl", matched_rule_id="__no_match__", reason="no routing rule matched")
