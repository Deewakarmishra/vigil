"""Jinja2 template environment for the operator console."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def money(value: float | None) -> str:
    if not value:
        return "$0"
    return f"${value:,.2f}"


templates.env.filters["money"] = money
