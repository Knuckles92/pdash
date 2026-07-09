"""pydantic-settings configuration for the MCP server."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PDASH_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Backend (FastAPI) base URL.
    backend_url: str = Field(default="http://localhost:8080")

    # Service secret printed by `python -m app.cli init` on the backend.
    service_secret: str = Field(default="")

    # MCP server bind.
    mcp_host: str = Field(default="127.0.0.1")
    mcp_port: int = Field(default=8090)

    # Logging.
    log_level: str = Field(default="INFO")

    # Auth-cache TTL: how long a resolved (api_key -> agent_info) entry stays
    # warm. Revocation propagates within this window (≤30s).
    auth_cache_ttl_s: float = Field(default=30.0)

    # Idempotency dedupe window: when the calling agent doesn't pass an
    # idempotency_key, the MCP server auto-generates one and caches
    # (agent_id, tool, args_hash) -> key for this many seconds so rapid
    # retries dedupe instead of creating two pending requests.
    idem_dedupe_ttl_s: float = Field(default=60.0)

    # httpx timeout for backend calls.
    backend_timeout_s: float = Field(default=15.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """For tests."""
    get_settings.cache_clear()
