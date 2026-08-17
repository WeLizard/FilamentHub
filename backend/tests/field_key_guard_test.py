"""The encryption key is checked against the data before anything is written."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.services.field_key_guard import (
    CANARY_KEY,
    FieldKeyMismatchError,
    verify_field_encryption_key,
)


@pytest.mark.asyncio
async def test_a_key_that_cannot_read_this_database_stops_the_application(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """Starting under another key is how a base of unreadable customers gets made.

    The application keeps serving, new records are sealed with the new key, the old
    ones stay sealed with the old, and no single key opens both. Refusing to start is
    the only point at which that is still preventable.
    """
    await verify_field_encryption_key(db_session)
    marker = await db_session.scalar(select(AppSetting).where(AppSetting.key == CANARY_KEY))
    assert marker is not None and marker.value

    monkeypatch.setattr(settings, "SECRET_KEY", "a-completely-different-secret-key")

    with pytest.raises(FieldKeyMismatchError):
        await verify_field_encryption_key(db_session)


@pytest.mark.asyncio
async def test_a_database_that_predates_encryption_is_not_a_mismatch(
    db_session: AsyncSession,
):
    """No marker means nothing was ever sealed here, not that the key is wrong."""
    await verify_field_encryption_key(db_session)
    await verify_field_encryption_key(db_session)

    marker = await db_session.scalar(select(AppSetting).where(AppSetting.key == CANARY_KEY))
    assert marker is not None
