"""Argon2id password hashing."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, candidate: str) -> bool:
    try:
        return _hasher.verify(stored_hash, candidate)
    except (VerifyMismatchError, InvalidHash):
        return False
