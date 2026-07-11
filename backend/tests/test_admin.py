"""Tests for admin API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_login(client: AsyncClient, suffix: str, role: str = "user") -> tuple[dict, int]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "username": f"user_{suffix}",
        "password": password, "role": role,
    })
    assert reg.status_code == 201
    user_id = reg.json()["id"]
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


async def _make_admin(db: AsyncSession, user_id: int) -> None:
    """Promote a user to admin directly in DB."""
    result = await db.execute(__import__("sqlalchemy").select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.role = UserRole.ADMIN
    await db.commit()


async def _create_brand(db: AsyncSession, name: str = "Test Brand") -> Brand:
    slug = name.lower().replace(" ", "-")
    brand = Brand(name=name, slug=slug, active=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


async def _create_filament(db: AsyncSession, brand_id: int) -> Filament:
    filament = Filament(
        brand_id=brand_id, name="Test Filament",
        slug="test-filament-admin", material_type="PLA", active=True,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


async def _create_preset(db: AsyncSession, filament_id: int, user_id: int,
                          status: PresetModerationStatus = PresetModerationStatus.PENDING) -> Preset:
    preset = Preset(
        filament_id=filament_id,
        user_id=user_id,
        name="Admin Test Preset",
        is_official=False,
        active=True,
        moderation_status=status,
        extruder_temp=200.0,
        bed_temp=60.0,
        flow_rate=100.0,
        fan_speed=100,
        retraction_length=1.0,
        retraction_speed=45.0,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_endpoints_require_auth(client: AsyncClient):
    """Unauthenticated requests to admin endpoints return 401."""
    response = await client.get("/api/v1/admin/brands")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin_role(client: AsyncClient):
    """Regular user gets 403 on admin endpoints."""
    headers, _ = await _register_and_login(client, "admin-regular")
    response = await client.get("/api/v1/admin/brands", headers=headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Brands
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_brands(client: AsyncClient, db_session: AsyncSession):
    """Admin can list brands."""
    headers, user_id = await _register_and_login(client, "admin-brands")
    await _make_admin(db_session, user_id)
    await _create_brand(db_session, "Listed Brand")

    response = await client.get("/api/v1/admin/brands", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_admin_verify_brand(client: AsyncClient, db_session: AsyncSession):
    """Admin can verify a brand."""
    headers, user_id = await _register_and_login(client, "admin-verify")
    await _make_admin(db_session, user_id)
    brand = await _create_brand(db_session, "Verify Brand")
    assert brand.verified is False

    response = await client.post(f"/api/v1/admin/brands/{brand.id}/verify", headers=headers)
    assert response.status_code == 200
    assert response.json()["verified"] is True


@pytest.mark.asyncio
async def test_admin_unverify_brand(client: AsyncClient, db_session: AsyncSession):
    """Admin can unverify a brand."""
    headers, user_id = await _register_and_login(client, "admin-unverify")
    await _make_admin(db_session, user_id)

    brand = Brand(name="Unverify Brand", slug="unverify-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await client.post(f"/api/v1/admin/brands/{brand.id}/unverify", headers=headers)
    assert response.status_code == 200
    assert response.json()["verified"] is False


@pytest.mark.asyncio
async def test_admin_verify_brand_not_found(client: AsyncClient, db_session: AsyncSession):
    """404 when verifying non-existent brand."""
    headers, user_id = await _register_and_login(client, "admin-verify-404")
    await _make_admin(db_session, user_id)

    response = await client.post("/api/v1/admin/brands/99999/verify", headers=headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Preset moderation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_pending_presets(client: AsyncClient, db_session: AsyncSession):
    """Admin sees pending presets in moderation queue."""
    headers, user_id = await _register_and_login(client, "admin-pending")
    await _make_admin(db_session, user_id)
    brand = await _create_brand(db_session, "Pending Brand")
    filament = await _create_filament(db_session, brand.id)
    await _create_preset(db_session, filament.id, user_id, PresetModerationStatus.PENDING)

    response = await client.get("/api/v1/admin/presets/pending", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_admin_approve_preset(client: AsyncClient, db_session: AsyncSession):
    """Admin can approve a pending preset."""
    headers, user_id = await _register_and_login(client, "admin-approve")
    await _make_admin(db_session, user_id)
    brand = await _create_brand(db_session, "Approve Brand")
    filament = await _create_filament(db_session, brand.id)
    preset = await _create_preset(db_session, filament.id, user_id, PresetModerationStatus.PENDING)

    response = await client.post(f"/api/v1/admin/presets/{preset.id}/approve", headers=headers)
    assert response.status_code == 200
    assert response.json()["moderation_status"] == "approved"


@pytest.mark.asyncio
async def test_admin_reject_preset(client: AsyncClient, db_session: AsyncSession):
    """Admin can reject a preset with a reason."""
    headers, user_id = await _register_and_login(client, "admin-reject")
    await _make_admin(db_session, user_id)
    brand = await _create_brand(db_session, "Reject Brand")
    filament = await _create_filament(db_session, brand.id)
    preset = await _create_preset(db_session, filament.id, user_id, PresetModerationStatus.PENDING)

    response = await client.post(
        f"/api/v1/admin/presets/{preset.id}/reject",
        headers=headers,
        params={"reason": "Incorrect settings"},
    )
    assert response.status_code == 200
    assert response.json()["moderation_status"] == "rejected"


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_list_users(client: AsyncClient, db_session: AsyncSession):
    """Admin can list users."""
    headers, user_id = await _register_and_login(client, "admin-list-users")
    await _make_admin(db_session, user_id)

    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_admin_deactivate_and_activate_user(client: AsyncClient, db_session: AsyncSession):
    """Admin can deactivate and then reactivate a user."""
    admin_headers, admin_id = await _register_and_login(client, "admin-deact")
    await _make_admin(db_session, admin_id)
    _, target_id = await _register_and_login(client, "admin-target-deact")

    deact = await client.post(f"/api/v1/admin/users/{target_id}/deactivate", headers=admin_headers)
    assert deact.status_code == 200
    assert deact.json()["active"] is False

    act = await client.post(f"/api/v1/admin/users/{target_id}/activate", headers=admin_headers)
    assert act.status_code == 200
    assert act.json()["active"] is True


@pytest.mark.asyncio
async def test_admin_promote_and_demote_user(client: AsyncClient, db_session: AsyncSession):
    """Admin can promote user to admin and demote back."""
    admin_headers, admin_id = await _register_and_login(client, "admin-promote")
    await _make_admin(db_session, admin_id)
    _, target_id = await _register_and_login(client, "admin-target-promote")

    promote = await client.post(f"/api/v1/admin/users/{target_id}/promote-admin", headers=admin_headers)
    assert promote.status_code == 200
    assert promote.json()["role"] == "admin"

    demote = await client.post(f"/api/v1/admin/users/{target_id}/demote-to-user", headers=admin_headers)
    assert demote.status_code == 200
    assert demote.json()["role"] == "user"


@pytest.mark.asyncio
async def test_admin_user_not_found(client: AsyncClient, db_session: AsyncSession):
    """404 when acting on non-existent user."""
    headers, user_id = await _register_and_login(client, "admin-user-404")
    await _make_admin(db_session, user_id)

    response = await client.post("/api/v1/admin/users/99999/activate", headers=headers)
    assert response.status_code == 404
