"""Quote details are stored so a leaked database copy cannot be read."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import FieldDecryptionError, decrypt_field, encrypt_field
from app.models.calculator_profile import UserCalculatorProfile
from app.models.user import User
from app.services import subscription_service


@pytest.fixture(autouse=True)
def restore_subscription_settings_cache():
    original = dict(subscription_service._settings_cache)
    yield
    subscription_service._settings_cache.clear()
    subscription_service._settings_cache.update(original)


@pytest.mark.asyncio
async def test_what_a_person_typed_is_not_what_the_table_holds(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)

    written = await auth_client.put(
        "/api/v1/calculator/profile",
        json={
            "seller_name": "ООО «Ромашка»",
            "seller_inn": "7701234567",
            "seller_phone": "+7 900 000-00-00",
            "payment_terms": "Оплата в течение 5 дней",
        },
    )
    assert written.status_code == 200
    # Read back through the API: the owner sees exactly what they typed.
    assert written.json()["seller_inn"] == "7701234567"

    stored = await db_session.scalar(
        select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == auth_user.id)
    )
    await db_session.refresh(stored)
    for column in ("seller_name", "seller_inn", "seller_phone", "payment_terms"):
        raw = getattr(stored, column)
        assert raw.startswith("fh1:"), column
    assert "7701234567" not in stored.seller_inn
    assert "Ромашка" not in stored.seller_name

    read = await auth_client.get("/api/v1/calculator/profile")
    assert read.json()["seller_name"] == "ООО «Ромашка»"
    assert read.json()["payment_terms"] == "Оплата в течение 5 дней"


@pytest.mark.asyncio
async def test_rows_written_before_encryption_still_read(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    """Existing profiles hold plain text; they must not turn into garbage."""
    await subscription_service.set_paywall_enforced(db_session, False)
    profile = UserCalculatorProfile(user_id=auth_user.id, seller_name="Иванов Иван")
    db_session.add(profile)
    await db_session.commit()

    read = await auth_client.get("/api/v1/calculator/profile")

    assert read.status_code == 200
    assert read.json()["seller_name"] == "Иванов Иван"


def test_the_empty_value_stays_empty() -> None:
    assert encrypt_field("") == ""
    assert decrypt_field("") == ""
    assert decrypt_field(None) == ""


def test_a_value_survives_the_round_trip() -> None:
    for value in ("ИП Петров", "+7 (900) 000-00-00", "Условия: 50% предоплата, 50% по факту"):
        assert decrypt_field(encrypt_field(value)) == value


@pytest.mark.parametrize("stored", ["fh1:not-a-real-token", "fh1:повреждено"])
def test_an_unreadable_value_is_not_disguised_as_empty(stored: str) -> None:
    with pytest.raises(FieldDecryptionError):
        decrypt_field(stored)


@pytest.mark.asyncio
async def test_an_unreadable_profile_returns_an_explicit_failure(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)
    profile = UserCalculatorProfile(
        user_id=auth_user.id,
        seller_name="fh1:not-a-real-token",
    )
    db_session.add(profile)
    await db_session.commit()

    response = await auth_client.get("/api/v1/calculator/profile")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "ERR_PROTECTED_DATA_UNREADABLE"
