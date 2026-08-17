"""Encrypt the few stored fields that would hurt if a database copy leaked.

This is not protection from FilamentHub itself — the server holds the key and
must be able to show a person their own details. It is protection from a dump
of the database ending up somewhere it should not: on its own, the dump reads
as noise.

Values are stored as "fh1:<token>". Anything without that prefix is read as
plain text, so existing rows keep working and a rollback loses nothing.

The key is its own setting rather than ``SECRET_KEY`` itself, because that one also
signs tokens: a leak forces it to change, and tying the data to it would mean losing
every protected field to answer an incident. Older keys stay readable through
``FIELD_ENCRYPTION_PREVIOUS_KEYS`` until what they wrote has been rewritten.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "fh1:"


class FieldDecryptionError(RuntimeError):
    """Raised when protected stored data cannot be recovered."""


def _field_keys() -> list[str]:
    """Keys this deployment may read with, the first of which it writes with.

    An empty ``FIELD_ENCRYPTION_KEY`` means the key is derived from ``SECRET_KEY``,
    which is how every database written before the split was encrypted.
    """
    primary = settings.FIELD_ENCRYPTION_KEY or settings.SECRET_KEY
    return [primary, *settings.FIELD_ENCRYPTION_PREVIOUS_KEYS]


def _fernet(key: str) -> Fernet:
    digest = hashlib.sha256(f"field-encryption:{key}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _cipher() -> MultiFernet:
    """Write with the current key, read with any key still listed.

    Without the older keys a rotation is a one-way trip: everything already stored
    becomes noise the moment the key changes, with no way back and no migration path.
    """
    return MultiFernet([_fernet(key) for key in _field_keys()])


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
    # Tied to the same key as the ciphertext, so there is one thing to rotate rather
    # than two. Changing it invalidates stored indexes, which are rebuilt from the
    # plaintext the application can still read.
    key = hashlib.sha256(
        f"field-blind-index:{_field_keys()[0]}".encode("utf-8")
    ).digest()
    message = f"{context}\0{value}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()
