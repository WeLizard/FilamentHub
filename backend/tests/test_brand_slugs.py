"""Regression tests for canonical brand URLs and historical redirects."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.brand_slug_redirect import BrandSlugRedirect
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.user import User


@pytest.mark.asyncio
async def test_brand_creation_uses_server_transliteration(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/brands/",
        json={"name": "НИТ"},
    )

    assert response.status_code == 201
    assert response.json()["slug"] == "nit"


@pytest.mark.asyncio
async def test_brand_request_gets_server_slug_when_omitted(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/brand-requests/",
        json={
            "request_type": "create",
            "new_brand_name": "Пластик Про",
            "proof_text": "Official manufacturer registration details",
        },
    )

    assert response.status_code == 201
    assert response.json()["new_brand_slug"] == "plastik-pro"


@pytest.mark.asyncio
async def test_admin_slug_rename_preserves_all_old_routes(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Canonical Brand", slug="canonical-old", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    renamed = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/slug",
        json={"slug": "canonical-new", "expected_current_slug": "canonical-old"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["slug"] == "canonical-new"

    renamed_again = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/slug",
        json={"slug": "canonical-final", "expected_current_slug": "canonical-new"},
    )
    assert renamed_again.status_code == 200
    assert renamed_again.json()["slug"] == "canonical-final"

    for identifier in (str(brand.id), "canonical-old", "canonical-new", "canonical-final"):
        resolved = await admin_client.get(f"/api/v1/brands/{identifier}")
        assert resolved.status_code == 200
        assert resolved.json()["id"] == brand.id
        assert resolved.json()["slug"] == "canonical-final"

    aliases = set(
        (
            await db_session.scalars(
                select(BrandSlugRedirect.old_slug).where(
                    BrandSlugRedirect.brand_id == brand.id
                )
            )
        ).all()
    )
    assert aliases == {"canonical-old", "canonical-new"}


@pytest.mark.asyncio
async def test_slug_change_requires_dedicated_fresh_flow(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Protected URL", slug="protected-url", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    generic = await admin_client.patch(
        f"/api/v1/admin/brands/{brand.id}",
        json={"slug": "silent-change"},
    )
    assert generic.status_code == 409
    assert generic.json()["detail"]["code"] == "ERR_BRAND_SLUG_RENAME_REQUIRED"

    stale = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/slug",
        json={"slug": "explicit-change", "expected_current_slug": "wrong-current"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "ERR_BRAND_SLUG_STALE"


@pytest.mark.asyncio
async def test_old_slug_is_reserved_and_numeric_slug_is_rejected(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Reserved Owner", slug="reserved-old", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    response = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/slug",
        json={"slug": "reserved-new", "expected_current_slug": "reserved-old"},
    )
    assert response.status_code == 200

    suggestion = await admin_client.get(
        "/api/v1/brands/slug-suggestion",
        params={"name": "Reserved Old"},
    )
    assert suggestion.status_code == 200
    assert suggestion.json()["slug"] == "reserved-old-2"

    reserved = await admin_client.post(
        "/api/v1/brands/",
        json={"name": "Other Brand", "slug": "reserved-old"},
    )
    assert reserved.status_code == 400
    assert reserved.json()["detail"]["code"] == "ERR_BRAND_SLUG_EXISTS"

    numeric = await admin_client.post(
        "/api/v1/brands/",
        json={"name": "Numeric Brand", "slug": "12345"},
    )
    assert numeric.status_code == 400
    assert numeric.json()["detail"]["code"] == "ERR_BRAND_SLUG_INVALID"


@pytest.mark.asyncio
async def test_employee_count_uses_organization_membership_not_active_brand_pointer(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    organization = Organization(
        name="Multi Brand Company",
        slug="multi-brand-company",
        created_by_id=admin_user.id,
    )
    db_session.add(organization)
    await db_session.flush()
    brand = Brand(
        name="Membership Brand",
        slug="membership-brand",
        organization_id=organization.id,
        active=True,
    )
    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=admin_user.id,
        role=OrganizationMemberRole.OWNER,
        all_brands=True,
        active=True,
    )
    db_session.add_all([brand, membership])
    await db_session.commit()
    await db_session.refresh(brand)

    assert admin_user.brand_id is None
    response = await admin_client.get(
        f"/api/v1/brands/{brand.slug}",
        params={"include_employees_count": True},
    )
    assert response.status_code == 200
    assert response.json()["employees_count"] == 1
