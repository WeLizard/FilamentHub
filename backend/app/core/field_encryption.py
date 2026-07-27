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
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "fh1:"


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
    except (InvalidToken, ValueError):
        logger.warning("Could not decrypt a stored field", exc_info=True)
        return ""
