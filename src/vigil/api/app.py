"""FastAPI application factory for the Vigil operator console."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vigil.api.routers import console, health
from vigil.config.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Vigil — Client Intake & Matter-Triage Agent", version="0.1.0")

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(health.router)
    app.include_router(console.router)
    return app


app = create_app()
