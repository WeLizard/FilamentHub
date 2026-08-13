"""Encrypt the few stored fields that would hurt if a database copy leaked.

This is not protection from FilamentHub itself — the server holds the key and
must be able to show a person their own details. It is protection from a dump
of the database ending up somewhere it should not: on its own, the dump reads
as noise.

Values are stored as "fh1:<token>". Anything without that prefix is read as
plain text, so existing rows keep working and a rollback loses nothing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "fh1:"


class FieldDecryptionError(RuntimeError):
    """Raised when protected stored data cannot be recovered."""


def _cipher() -> Fernet:
    digest = hashlib.sha256(f"field-encryption:{settings.SECRET_KEY}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_field(value: str | None) -> str:
    """Turn a stored value into ciphertext. Empty stays empty."""
    if not value:
        return ""
    return PREFIX + _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_field(value: str | None) -> str:
    """Read a stored value, encrypted or not."""
    if not value:
        return ""
    if not value.startswith(PREFIX):
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        logger.warning("Could not decrypt a stored field", exc_info=True)
        raise FieldDecryptionError("Protected stored data is unreadable") from exc


def blind_index(value: str, *, context: str) -> str:
    """Return a keyed, non-reversible equality index for protected data.

    A plain SHA-256 hash is not sufficient for LAN endpoints: the private IPv4
    search space is small enough to enumerate from a leaked database.  This
    HMAC lets the application compare encrypted values without making that
    offline dictionary attack useful.
    """
    key = hashlib.sha256(
        f"field-blind-index:{settings.SECRET_KEY}".encode("utf-8")
    ).digest()
    message = f"{context}\0{value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()
