"""Fernet-based symmetric encryption for connector credentials.

Falls back to a deterministic dev key when FERNET_KEY is a placeholder, so
the demo runs without generating a key. Never use the dev key in production.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from vigil.config import get_settings


def _dev_key() -> bytes:
    """Deterministic key derived from the session secret — dev/demo only."""

    secret = get_settings().session_secret.encode("utf-8")
    digest = hashlib.sha256(secret or b"vigil-dev").digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    key = get_settings().fernet_key
    if not key or key == "__PLACEHOLDER__":
        return Fernet(_dev_key())
    return Fernet(key.encode("utf-8"))


def encrypt_value(plaintext: str) -> str:
    return _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str) -> str:
    return _cipher().decrypt(token.encode("utf-8")).decode("utf-8")


def mask_secret(value: str, show_last: int = 4) -> str:
    """Mask a secret for display: ``****...****-LAST4``."""

    if not value:
        return ""
    if len(value) <= show_last:
        return "*" * len(value)
    return f"****...****-{value[-show_last:]}"
