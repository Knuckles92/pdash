"""Secret redaction for response payloads."""

from __future__ import annotations

from typing import Any

# Keys that look like secrets get redacted on read.
SECRET_KEYS = {
    "secret",
    "token",
    "api_key",
    "password",
    "bearer",
    "authorization",
    "auth",
    "private_key",
    "client_secret",
}

REDACTED = "***REDACTED***"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if k.lower() in SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
