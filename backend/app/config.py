"""Application configuration via pydantic-settings."""

from __future__ import annotations

import json
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Read from environment variables with prefix PDASH_."""

    model_config = SettingsConfigDict(
        env_prefix="PDASH_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./pdash.db",
        description="SQLAlchemy async URL.",
    )
    # When set, overrides database_url to point at a specific file path.
    database_path: str | None = Field(default=None)

    # Auth / session
    session_cookie_name: str = "session"
    csrf_cookie_name: str = "csrf_token"
    session_lifetime_seconds: int = Field(
        default=int(timedelta(days=30).total_seconds()),
        description="Signed session cookie lifetime.",
    )
    # If set, used as the signing secret instead of the value persisted in kv_settings.
    # Primarily for tests.
    signing_secret_override: str | None = None

    # App
    cors_origins: list[str] = Field(default_factory=list)
    cookie_secure: bool = False  # True in production (Caddy/HTTPS)
    docs_enabled: bool = True

    idempotency_ttl_seconds: int = Field(
        default=int(timedelta(days=30).total_seconds()),
        description=(
            "Retention for request_idempotency rows. Sweeper not implemented yet."
        ),
    )
    audit_blob_threshold_bytes: int = Field(
        default=32 * 1024,
        description="Max inline activity_log payload; larger summaries spill to audit_blobs.",
    )
    pending_ttl_seconds: int = Field(
        default=int(timedelta(days=7).total_seconds()),
        description="Offset for approval_request.expires_at on pending rows.",
    )

    # Agent self-registration (agent-first MCP onboarding). A keyless client can
    # request registration via the ungated bootstrap surface; requests always
    # land pending for the admin. These bound abuse of that ungated path.
    agent_registration_max_pending: int = Field(
        default=25,
        description=(
            "Max outstanding pending agent self-registration requests before new "
            "ones are refused (bounds flooding of the admin approval queue)."
        ),
    )
    agent_registration_ttl_seconds: int = Field(
        default=int(timedelta(days=7).total_seconds()),
        description="How long a pending agent self-registration stays claimable before it expires.",
    )

    # Files (agent file-drop). Agents write into the inbox dir on a shared host
    # mount; registered files are moved into the managed store dir and served.
    # Both default to siblings of pdash.db inside the data dir.
    files_inbox_path: str | None = Field(default=None)
    files_store_path: str | None = Field(default=None)
    file_max_bytes: int = Field(
        default=25 * 1024 * 1024,
        description="Maximum size (bytes) of a file an agent may register.",
    )
    file_mime_allowlist: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description=(
            "If non-empty, only these MIME types may be registered. Empty means "
            "any type is accepted (risky types are still force-downloaded on serve)."
        ),
    )

    # Dashboard screenshots (agent visibility).
    # When an agent asks for a screenshot, the backend mints a short-lived admin
    # session cookie and asks the screenshot sidecar to render the live frontend
    # page in headless Chromium. Leave screenshot_service_url empty to disable
    # the feature entirely (the endpoint then returns 501 screenshot.unavailable).
    frontend_url: str = Field(
        default="http://frontend:3000",
        description="Base URL of the Next.js frontend, reachable from the backend.",
    )
    screenshot_service_url: str | None = Field(
        default=None,
        description="Base URL of the screenshot sidecar (e.g. http://screenshot:9000). Empty disables screenshots.",
    )
    screenshot_timeout_seconds: float = Field(default=30.0)
    screenshot_session_ttl_seconds: int = Field(
        default=120,
        description="Lifetime of the throwaway admin session cookie minted for a screenshot.",
    )
    screenshot_default_viewport_width: int = Field(default=1280)

    # MCP server (the FastMCP translator service). The backend probes its
    # `/info` endpoint to power the admin "MCP control center" UI. In compose
    # this is set to http://mcp:8090; dev default targets a native `make dev`.
    mcp_url: str = Field(
        default="http://localhost:8090",
        description="Base URL of the MCP server, reachable from the backend.",
    )
    mcp_probe_timeout_seconds: float = Field(default=5.0)

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("file_mime_allowlist", mode="before")
    @classmethod
    def _parse_file_mime_allowlist(cls, value: object) -> object:
        if value is None:
            return []
        if not isinstance(value, str):
            return value

        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return parsed
        return [item.strip() for item in raw.split(",") if item.strip()]

    def resolved_database_url(self) -> str:
        if self.database_path:
            p = Path(self.database_path).resolve()
            return f"sqlite+aiosqlite:///{p}"
        return self.database_url

    def resolved_database_path(self) -> Path | None:
        if self.database_path:
            return Path(self.database_path).resolve()
        # Try to parse from sqlite URL
        url = self.database_url
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix):
            return Path(url[len(prefix):]).resolve()
        return None

    def _files_base_dir(self) -> Path:
        """Directory the inbox/store default under (the data dir, beside pdash.db)."""
        db = self.resolved_database_path()
        return db.parent if db is not None else Path.cwd()

    def resolved_files_inbox_path(self) -> Path:
        if self.files_inbox_path:
            return Path(self.files_inbox_path).resolve()
        return (self._files_base_dir() / "inbox").resolve()

    def resolved_files_store_path(self) -> Path:
        if self.files_store_path:
            return Path(self.files_store_path).resolve()
        return (self._files_base_dir() / "files").resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()

def reset_settings_cache() -> None:
    """Clear cached settings (mostly for tests that monkey-patch env)."""
    get_settings.cache_clear()
