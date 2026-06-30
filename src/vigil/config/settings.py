"""Typed application settings sourced from environment variables / .env.

Every field has a safe default that lets the platform boot in mock mode
without any real third-party credentials, so the demo works out of the box.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "vigil"
    app_host: str = Field(default="127.0.0.1")
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    # --- Security ---
    fernet_key: str = "__PLACEHOLDER__"
    session_secret: str = "__PLACEHOLDER__"

    # --- Database ---
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "vigil"
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_pool_size: int = 5
    postgres_pool_max_overflow: int = 10

    # --- Redis / RQ (production async path) ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    rq_queue_default: str = "vigil:default"

    # --- Connector mode ---
    connector_mode: Literal["mock", "live"] = "mock"

    # --- Agent providers ---
    use_llm: bool = False
    anthropic_api_key: str = "__PLACEHOLDER__"
    anthropic_model: str = "claude-sonnet-4-6"

    # --- AML / triage policy knobs ---
    auto_min_confidence: float = 0.60  # below this, route to an officer
    ctr_threshold: float = 10000.0  # CTR reporting threshold (structuring sits just beneath)
    baseline_tolerance: float = 1.2  # observed within this × the expected ceiling reads as explained
    structuring_min_count: int = 3  # cash deposits under CTR to flag structuring

    # --- Live connectors ---
    tm_provider: Literal["mock", "actimize", "unit21", "inhouse"] = "mock"
    tm_api_key: str = "__PLACEHOLDER__"
    casemgmt_provider: Literal["mock", "fincen_efile"] = "mock"
    casemgmt_api_key: str = "__PLACEHOLDER__"

    # --- Demo seed ---
    demo_brand_slug: str = "meridian"
    demo_admin_email: str = "admin@vigil.demo"
    demo_admin_password: str = "demo-admin-password"

    # ---- derived helpers ----

    @property
    def database_url(self) -> str:
        pw = f":{self.postgres_password}" if self.postgres_password else ""
        return (
            f"postgresql+psycopg2://{self.postgres_user}{pw}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def server_url(self) -> str:
        """Connection URL to the `postgres` maintenance DB (for CREATE DATABASE)."""
        pw = f":{self.postgres_password}" if self.postgres_password else ""
        return f"postgresql+psycopg2://{self.postgres_user}{pw}" f"@{self.postgres_host}:{self.postgres_port}/postgres"

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_mock(self) -> bool:
        return self.connector_mode == "mock"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance. Tests clear via ``get_settings.cache_clear()``."""

    return Settings()
