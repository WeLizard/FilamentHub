"""Tests for QR backfill on brand verification.

Materials created before a brand is verified (by users or the brand itself)
get their QR codes when the brand becomes verified or the brand triggers a
backfill. A pre-existing code is never overwritten.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestType
from app.models.brand_territorial_grant import BrandTerritorialGrant, GrantSource, GrantStatus
from app.models.filament import Filament
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.user import User, UserRole
from app.services import qr_service
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)
from app.services.qr_service import backfill_brand_qr_codes, repair_verified_brand_qr_codes


async def _brand_with_filaments(db: AsyncSession, *, verified: bool, tag: str) -> Brand:
    brand = Brand(name=f"BF {tag}", slug=f"bf-{tag}", active=True, verified=verified)
    db.add(brand)
    await db.flush()
    for i in range(2):
        db.add(Filament(
            brand_id=brand.id, name=f"BF {tag} {i}", slug=f"bf-{tag}-{i}",
            material_type="PLA", active=True,
        ))
    db.add(Filament(
        brand_id=brand.id, name=f"BF {tag} has", slug=f"bf-{tag}-has",
        material_type="PLA", active=True, qr_code=f"already-{tag}",
    ))
    await db.commit()
    await db.refresh(brand)
    return brand


@pytest.mark.asyncio
async def test_backfill_assigns_only_missing(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    brand = await _brand_with_filaments(db_session, verified=True, tag="v")

    assigned = await backfill_brand_qr_codes(brand, db_session)
    await db_session.commit()

    assert assigned == 2
    still_missing = await db_session.scalar(
        select(Filament.id).where(Filament.brand_id == brand.id, Filament.qr_code.is_(None))
    )
    assert still_missing is None
    # Pre-existing code untouched.
    kept = await db_session.scalar(
        select(Filament.qr_code).where(Filament.slug == "bf-v-has")
    )
    assert kept == "already-v"


@pytest.mark.asyncio
async def test_backfill_noop_for_unverified(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    brand = await _brand_with_filaments(db_session, verified=False, tag="u")
    assert await backfill_brand_qr_codes(brand, db_session) == 0


@pytest.mark.asyncio
async def test_startup_repair_restores_only_verified_brand_codes(
    db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    verified = await _brand_with_filaments(db_session, verified=True, tag="repair-v")
    unverified = await _brand_with_filaments(db_session, verified=False, tag="repair-u")

    assigned = await repair_verified_brand_qr_codes(db_session)
    await db_session.commit()

    assert assigned == 2
    assert await db_session.scalar(
        select(Filament.id).where(
            Filament.brand_id == verified.id,
            Filament.qr_code.is_(None),
        )
    ) is None
    assert await db_session.scalar(
        select(Filament.id).where(
            Filament.brand_id == unverified.id,
            Filament.qr_code.is_(None),
        )
    ) is not None


@pytest.mark.asyncio
async def test_backfill_endpoint_forbidden_for_non_owner(client: AsyncClient, db_session: AsyncSession):
    brand = Brand(name="Other Brand", slug="other-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    email, password = "qr-backfill@example.com", "testpassword123"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": "qr_backfill", "password": password, "role": "user",
        "terms_accepted": True,
        "personal_data_consent": True,
        "terms_version": "2026-08-01",
        "personal_data_consent_version": "2026-08-01",
        "privacy_policy_version": "2026-08-01",
        "legal_language": "en",
    })
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(f"/api/v1/brands/{brand.id}/backfill-qr", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_any_active_representative_gets_automatic_and_manual_qr_recovery(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    brand = await _brand_with_filaments(db_session, verified=True, tag="regional")
    organization = Organization(name="Regional QR", slug="regional-qr")
    user = User(
        email="regional-qr@example.com",
        username="regional_qr",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        role=UserRole.USER,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add_all([organization, user])
    await db_session.flush()
    user.active_organization_id = organization.id
    db_session.add_all([
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        ),
        BrandTerritorialGrant(
            brand_id=brand.id,
            organization_id=organization.id,
            country="DE",
            status=GrantStatus.active,
            source=GrantSource.application,
            create_filaments=False,
        ),
    ])
    await db_session.commit()

    from app.core.security import create_access_token

    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}
    filament_id = await db_session.scalar(
        select(Filament.id)
        .where(Filament.brand_id == brand.id, Filament.qr_code.is_(None))
        .order_by(Filament.id)
    )
    assert filament_id is not None

    # A direct label download repairs its own missing code.
    download = await client.get(
        f"/api/v1/qr/filaments/{filament_id}/qr-code/download",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "image/png"

    # The visible bulk action remains a fallback for the rest of the brand.
    response = await client.post(
        f"/api/v1/brands/{brand.id}/backfill-qr",
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["assigned"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_prefix",
    ["/api/v1/admin/brand-requests", "/api/v1/brand-requests"],
)
async def test_approved_existing_brand_claim_backfills_qr_codes(
    endpoint_prefix: str,
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Both legacy moderation routes verify the claimed brand and issue its QR codes."""
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *args, **kwargs: [])
    suffix = endpoint_prefix.replace("/", "-").strip("-")
    brand = Brand(
        name=f"Claimed {suffix}",
        slug=f"claimed-{suffix}",
        active=True,
        verified=False,
    )
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Claimed PLA",
        slug=f"claimed-pla-{suffix}",
        material_type="PLA",
        active=True,
    )
    claimant = User(
        email=f"claimant-{suffix}@example.com",
        username="claimant",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.USER,
    )
    db_session.add(claimant)
    await db_session.flush()
    request = BrandRequest(
        user_id=claimant.id,
        request_type=BrandRequestType.JOIN,
        brand_id=brand.id,
    )
    db_session.add_all([filament, request])
    await db_session.commit()

    response = await admin_client.patch(
        f"{endpoint_prefix}/{request.id}",
        json={"status": "approved"},
    )
    assert response.status_code == 200

    await db_session.refresh(brand)
    qr_code = await db_session.scalar(
        select(Filament.qr_code).where(Filament.id == filament.id)
    )
    assert brand.verified is True
    assert qr_code
    await db_session.refresh(claimant)
    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == claimant.id,
            OrganizationMembership.organization_id == brand.organization_id,
        )
    )
    assert brand.organization_id is not None
    assert claimant.brand_id == brand.id
    assert claimant.role == UserRole.BRAND
    assert membership is not None
    assert membership.role == OrganizationMemberRole.OWNER
    assert membership.all_brands is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_prefix",
    ["/api/v1/admin/brand-requests", "/api/v1/brand-requests"],
)
async def test_approved_new_catalog_brand_does_not_grant_representation(
    endpoint_prefix: str,
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    """Adding a missing catalog brand does not create company authority."""
    suffix = endpoint_prefix.replace("/", "-").strip("-")
    claimant = User(
        email=f"new-claimant-{suffix}@example.com",
        username="new_claimant",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.USER,
    )
    db_session.add(claimant)
    await db_session.flush()
    request = BrandRequest(
        user_id=claimant.id,
        request_type=BrandRequestType.CREATE,
        new_brand_name=f"New Claim {suffix}",
        new_brand_slug=f"new-claim-{suffix}",
    )
    db_session.add(request)
    await db_session.commit()

    response = await admin_client.patch(
        f"{endpoint_prefix}/{request.id}",
        json={"status": "approved"},
    )
    assert response.status_code == 200

    brand = await db_session.scalar(
        select(Brand).where(Brand.slug == request.new_brand_slug)
    )
    assert brand is not None
    assert brand.verified is True
    assert brand.organization_id is None

    await db_session.refresh(claimant)
    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == claimant.id,
        )
    )
    assert claimant.brand_id is None
    assert claimant.active_organization_id is None
    assert claimant.role == UserRole.USER
    assert membership is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_prefix",
    ["/api/v1/admin/brand-requests", "/api/v1/brand-requests"],
)
async def test_approved_new_brand_claim_grants_owner_workspace(
    endpoint_prefix: str,
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """A reviewed create-and-claim request is not sent through moderation twice."""
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *args, **kwargs: [])
    suffix = endpoint_prefix.replace("/", "-").strip("-")
    claimant = User(
        email=f"owner-{suffix}@example.com",
        username=f"owner_{len(suffix)}",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.USER,
    )
    db_session.add(claimant)
    await db_session.flush()
    request = BrandRequest(
        user_id=claimant.id,
        request_type=BrandRequestType.CREATE,
        claim_scope="brand",
        new_brand_name=f"Owned Brand {suffix}",
        new_brand_slug=f"owned-brand-{suffix}",
    )
    db_session.add(request)
    await db_session.commit()

    response = await admin_client.patch(
        f"{endpoint_prefix}/{request.id}", json={"status": "approved"}
    )

    assert response.status_code == 200
    brand = await db_session.scalar(select(Brand).where(Brand.slug == request.new_brand_slug))
    assert brand is not None
    assert brand.organization_id is not None
    await db_session.refresh(claimant)
    assert claimant.brand_id == brand.id
    assert claimant.role == UserRole.BRAND
    membership = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == brand.organization_id,
            OrganizationMembership.user_id == claimant.id,
        )
    )
    assert membership is not None
    assert membership.role == OrganizationMemberRole.OWNER
    assert membership.all_brands is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_prefix",
    ["/api/v1/admin/brand-requests", "/api/v1/brand-requests"],
)
async def test_approved_new_representative_claim_grants_only_its_country(
    endpoint_prefix: str,
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """A reviewed territorial request creates a country-scoped grant."""
    from app.models.brand_territorial_grant import BrandTerritorialGrant

    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *args, **kwargs: [])
    suffix = endpoint_prefix.replace("/", "-").strip("-")
    claimant = User(
        email=f"representative-{suffix}@example.com",
        username=f"rep_{len(suffix)}",
        password_hash="$2b$12$test",
        active=True,
        role=UserRole.USER,
    )
    db_session.add(claimant)
    await db_session.flush()
    request = BrandRequest(
        user_id=claimant.id,
        request_type=BrandRequestType.CREATE,
        claim_scope="representative",
        country="DE",
        new_brand_name=f"Regional Brand {suffix}",
        new_brand_slug=f"regional-brand-{suffix}",
    )
    db_session.add(request)
    await db_session.commit()

    response = await admin_client.patch(
        f"{endpoint_prefix}/{request.id}", json={"status": "approved"}
    )

    assert response.status_code == 200
    brand = await db_session.scalar(select(Brand).where(Brand.slug == request.new_brand_slug))
    assert brand is not None
    grant = await db_session.scalar(
        select(BrandTerritorialGrant).where(BrandTerritorialGrant.brand_id == brand.id)
    )
    assert grant is not None
    assert grant.country == "DE"
    await db_session.refresh(claimant)
    assert claimant.brand_id == brand.id
    assert claimant.role == UserRole.BRAND
