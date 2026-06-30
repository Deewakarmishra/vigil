"""YAML loader for the routing policy DSL (content-hashed)."""

from __future__ import annotations

import hashlib

import yaml


def load_rules_from_yaml(text: str) -> tuple[list[dict], str]:
    """Parse policy YAML into a list of rule dicts + a content SHA-256."""

    data = yaml.safe_load(text) or {}
    rules = data.get("rules", [])
    if not isinstance(rules, list):
        raise ValueError("policy 'rules' must be a list")
    for r in rules:
        if "id" not in r or "route" not in r:
            raise ValueError(f"policy rule missing id/route: {r!r}")
        r.setdefault("when", {})
        r.setdefault("reason", r["id"])
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return rules, sha
