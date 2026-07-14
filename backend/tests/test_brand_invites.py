"""Tests for the brand invitation flow."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.organization import OrganizationMembership, OrganizationMemberRole
from app.core.security import create_access_token
from app.services import qr_service


@pytest.mark.asyncio
async def test_brand_invite_flow(admin_client: AsyncClient):
    """Admin issues an invite, accepts it, a verified brand is created, token burns.

    Uses a single client because admin_client/auth_client share one underlying
    client object and would clobber each other's auth header.
    """
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "admin_user@example.com", "brand_name": "Inv Brand", "expires_days": 7},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    assert created.json()["invite_url"].endswith(token)

    public = await admin_client.get(f"/api/v1/brand-invites/{token}")
    assert public.status_code == 200
    assert public.json()["valid"] is True
    assert public.json()["brand_name"] == "Inv Brand"
    assert public.json()["email"] == "a*********@example.com"

    accept = await admin_client.post(
        f"/api/v1/brand-invites/{token}/accept", json={"brand_name": "Tampered Brand"}
    )
    assert accept.status_code == 200
    assert accept.json()["brand_name"] == "Inv Brand"
    assert accept.json()["brand_id"] > 0
    assert accept.json()["organization_id"] > 0
    assert accept.json()["member_role"] == "owner"

    # Token is consumed for other users, while the same recipient can safely
    # retry after a dropped HTTP response without creating duplicate ownership.
    public_after = await admin_client.get(f"/api/v1/brand-invites/{token}")
    assert public_after.json()["valid"] is False

    again = await admin_client.post(
        f"/api/v1/brand-invites/{token}/accept", json={"brand_name": "Inv Brand"}
    )
    assert again.status_code == 200
    assert again.json()["brand_id"] == accept.json()["brand_id"]


@pytest.mark.asyncio
async def test_brand_invite_requires_admin(auth_client: AsyncClient):
    """A non-admin cannot create invites."""
    resp = await auth_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "x@example.com", "brand_name": "Example"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_brand_invite_transliterates_cyrillic_brand_slug(admin_client: AsyncClient):
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "admin_user@example.com", "brand_name": "НИТ", "expires_days": 7},
    )
    assert created.status_code == 201

    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={"brand_name": "НИТ"},
    )
    assert accepted.status_code == 200

    brand = await admin_client.get(f"/api/v1/brands/{accepted.json()['brand_id']}")
    assert brand.status_code == 200
    assert brand.json()["slug"] == "nit"


@pytest.mark.asyncio
async def test_existing_brand_invite_backfills_qr_codes(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Claiming a community brand makes its existing filament cards package-ready."""
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *args, **kwargs: [])
    brand = Brand(
        name="Community Brand",
        slug="community-brand-invite",
        active=True,
        verified=False,
    )
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Community PLA",
        slug="community-pla-invite",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()

    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={
            "email": "admin_user@example.com",
            "target_type": "existing",
            "brand_id": brand.id,
        },
    )
    assert created.status_code == 201

    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={},
    )
    assert accepted.status_code == 200
    assert accepted.json()["brand_id"] == brand.id

    await db_session.refresh(brand)
    qr_code = await db_session.scalar(
        select(Filament.qr_code).where(Filament.id == filament.id)
    )
    assert brand.verified is True
    assert qr_code

    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == accepted.json()["organization_id"],
        )
    )
    assert membership is not None
    assert membership.role == OrganizationMemberRole.OWNER
    assert membership.all_brands is True


@pytest.mark.asyncio
async def test_brand_invite_accepts_another_account_on_same_domain(admin_client: AsyncClient):
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "representative@example.com", "brand_name": "Domain Brand"},
    )
    assert created.status_code == 201

    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={},
    )

    assert accepted.status_code == 200
    assert accepted.json()["brand_name"] == "Domain Brand"


@pytest.mark.asyncio
async def test_brand_invite_rejects_account_from_another_domain(admin_client: AsyncClient):
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "representative@brand.example", "brand_name": "Bound Brand"},
    )
    assert created.status_code == 201

    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={},
    )

    assert accepted.status_code == 403
    assert accepted.json()["detail"]["code"] == "ERR_BRAND_INVITE_EMAIL_MISMATCH"


@pytest.mark.asyncio
async def test_first_representative_can_correct_community_brand_name_once(
    admin_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
    monkeypatch,
):
    """A claimed community page keeps its data and permits one official spelling correction."""
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *args, **kwargs: [])
    brand = Brand(
        name="PLastiq",
        slug="plastiq-community",
        active=True,
        verified=False,
    )
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PLA Community",
        slug="plastiq-pla-community",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    db_session.add(
        Brand(
            name="Existing Official Name",
            slug="existing-official-name",
            active=True,
            verified=True,
        )
    )
    await db_session.commit()

    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={
            "email": auth_user.email,
            "target_type": "existing",
            "brand_id": brand.id,
        },
    )
    assert created.status_code == 201

    admin_client.headers["Authorization"] = (
        f"Bearer {create_access_token({'sub': auth_user.email})}"
    )
    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={},
    )
    assert accepted.status_code == 200

    duplicate_name = await admin_client.patch(
        f"/api/v1/brands/{brand.id}",
        json={"name": "Existing Official Name"},
    )
    assert duplicate_name.status_code == 409
    assert duplicate_name.json()["detail"]["code"] == "ERR_BRAND_NAME_EXISTS"

    corrected = await admin_client.patch(
        f"/api/v1/brands/{brand.id}",
        json={"name": "PlastiQ"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["name"] == "PlastiQ"
    assert corrected.json()["slug"] == "plastiq-community"
    assert corrected.json()["name_correction_available"] is False

    filament_after = await db_session.get(Filament, filament.id)
    assert filament_after is not None
    assert filament_after.brand_id == brand.id

    second_correction = await admin_client.patch(
        f"/api/v1/brands/{brand.id}",
        json={"name": "PlastiQ Official"},
    )
    assert second_correction.status_code == 409
    assert second_correction.json()["detail"]["code"] == "ERR_BRAND_NAME_CORRECTION_USED"


@pytest.mark.asyncio
async def test_brand_invite_unknown_token(admin_client: AsyncClient):
    """An unknown token reports invalid, not a server error."""
    resp = await admin_client.get("/api/v1/brand-invites/nope-nope-nope")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
