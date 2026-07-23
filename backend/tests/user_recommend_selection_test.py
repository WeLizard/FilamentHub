"""Per-user catalog recommendation selection stored on the account.

The choice (physical printer + configuration) follows the account across
devices; it must reference the user's own printer/config, and null clears it.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice

URL = "/api/v1/auth/me"


async def _device(db: AsyncSession, user: User, name: str = "Voron") -> UserPrinterDevice:
    device = UserPrinterDevice(user_id=user.id, name=name)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def _profile(db: AsyncSession, user: User, slug: str) -> PrinterProfile:
    profile = PrinterProfile(owner_user_id=user.id, name=slug, slug=slug, active=True)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def _other_user(db: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"other{suffix}@example.com",
        username=f"other{suffix}",
        password_hash="$2b$12$test",
        active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_set_own_selection(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    device = await _device(db_session, auth_user)
    profile = await _profile(db_session, auth_user, "own-cfg")

    resp = await auth_client.patch(
        URL,
        json={
            "recommend_physical_printer_id": device.id,
            "recommend_printer_profile_id": profile.id,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommend_physical_printer_id"] == device.id
    assert body["recommend_printer_profile_id"] == profile.id


@pytest.mark.asyncio
async def test_foreign_device_rejected(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = await _other_user(db_session, "d")
    foreign_device = await _device(db_session, other, name="Not yours")

    resp = await auth_client.patch(
        URL, json={"recommend_physical_printer_id": foreign_device.id}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_foreign_profile_rejected(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = await _other_user(db_session, "p")
    foreign_profile = await _profile(db_session, other, "foreign-cfg")

    resp = await auth_client.patch(
        URL, json={"recommend_printer_profile_id": foreign_profile.id}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_clear_selection(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    device = await _device(db_session, auth_user)
    profile = await _profile(db_session, auth_user, "clear-cfg")
    await auth_client.patch(
        URL,
        json={
            "recommend_physical_printer_id": device.id,
            "recommend_printer_profile_id": profile.id,
        },
    )

    resp = await auth_client.patch(
        URL,
        json={
            "recommend_physical_printer_id": None,
            "recommend_printer_profile_id": None,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommend_physical_printer_id"] is None
    assert body["recommend_printer_profile_id"] is None
