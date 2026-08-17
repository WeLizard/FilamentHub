"""Refuse to run against data this key cannot read.

Protected fields are encrypted with a key derived from ``SECRET_KEY``. Starting with a
different one is not a harmless misconfiguration: the application keeps working, and
every record written from then on is sealed with the new key while the old ones stay
sealed with the old. Nothing complains until somebody opens a list and finds a customer
that can no longer be read — by which point both sets exist and neither key opens both.

So the key is checked once at startup against a value written the first time the
application ever ran. A mismatch stops the process instead of quietly producing a
second set of unreadable rows.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import FieldDecryptionError, decrypt_field, encrypt_field
from app.models.app_setting import AppSetting

logger = logging.getLogger(__name__)

CANARY_KEY = "field_encryption_canary_v1"
CANARY_PLAINTEXT = "filamenthub-field-encryption"


class FieldKeyMismatchError(RuntimeError):
    """The configured key cannot read what this database was written with."""


async def verify_field_encryption_key(db: AsyncSession) -> None:
    """Compare the running key against the one this database was sealed with.

    Writes the marker when it is missing, which covers both a fresh install and a
    database that predates encryption. Absence is not evidence of a wrong key.
    """
    row = await db.scalar(select(AppSetting).where(AppSetting.key == CANARY_KEY))

    if row is None or not row.value:
        marker = encrypt_field(CANARY_PLAINTEXT)
        if row is None:
            db.add(AppSetting(key=CANARY_KEY, value=marker))
        else:
            row.value = marker
        await db.commit()
        logger.info("Field encryption key recorded for this database")
        return

    try:
        recovered = decrypt_field(row.value)
    except FieldDecryptionError as exc:
        raise FieldKeyMismatchError(
            "SECRET_KEY does not match the key this database was encrypted with. "
            "Starting anyway would write records the previous key cannot read and "
            "leave the existing ones unreadable. Restore the previous SECRET_KEY, or "
            f"— if the change is deliberate and the old data is expendable — delete the "
            f"'{CANARY_KEY}' row from app_settings and accept that already encrypted "
            "fields stay unreadable."
        ) from exc

    if recovered != CANARY_PLAINTEXT:
        raise FieldKeyMismatchError(
            "The field encryption marker decrypted to an unexpected value; refusing to "
            "start rather than write data under a key of unknown provenance."
        )
