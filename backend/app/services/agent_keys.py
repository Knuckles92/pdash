"""Plaintext agent API key generation."""

from __future__ import annotations

import base64
import secrets

from ..auth.passwords import hash_password


def generate_agent_api_key() -> tuple[str, str]:
    """Return (plaintext, argon2_hash)."""
    raw = secrets.token_bytes(32)
    # base32 without padding, lowercased for readability.
    encoded = base64.b32encode(raw).rstrip(b"=").decode("ascii").lower()
    plaintext = f"hb_agt_{encoded}"
    return plaintext, hash_password(plaintext)
