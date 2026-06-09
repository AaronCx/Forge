"""Encrypt-at-rest helpers for provider API keys.

Values are encrypted with Fernet using a key derived from
``FORGE_ENCRYPTION_KEY``. When the env var is unset the helpers pass values
through unchanged (legacy plaintext behavior) and a startup warning is logged.
Decryption transparently falls back to treating the stored value as legacy
plaintext when it is not a valid Fernet token.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)


def _get_fernet():
    """Build a Fernet from FORGE_ENCRYPTION_KEY, or None when unset."""
    secret = os.environ.get("FORGE_ENCRYPTION_KEY", "")
    if not secret:
        return None
    from cryptography.fernet import Fernet

    # Accept any string secret — derive a urlsafe 32-byte Fernet key from it.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def warn_if_unconfigured() -> None:
    """Log a startup warning when encryption-at-rest is not configured."""
    if _get_fernet() is None:
        logger.warning(
            "FORGE_ENCRYPTION_KEY is not set — provider API keys will be stored "
            "in plaintext. Set FORGE_ENCRYPTION_KEY to enable encryption at rest."
        )


def encrypt_secret(value: str) -> str:
    """Encrypt ``value`` for storage; passthrough when no key is configured."""
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    encrypted: str = fernet.encrypt(value.encode()).decode()
    return encrypted


def decrypt_secret(value: str) -> str:
    """Decrypt a stored secret; legacy plaintext rows are returned unchanged."""
    if not value:
        return value
    fernet = _get_fernet()
    if fernet is None:
        return value
    try:
        decrypted: str = fernet.decrypt(value.encode()).decode()
        return decrypted
    except Exception:
        # Legacy plaintext row (or a value encrypted with a different key).
        return value
