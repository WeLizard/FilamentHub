"""Permissions and round-trip coverage for product-specific handling guidance."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.user import User
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)


async def _brand(db: AsyncSession, suffix: str) -> Brand:
    brand = Brand(name=f"Handling {suffix}", slug=f"handling-{suffix}", active=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


async def _representative_headers(db: AsyncSession, brand: Brand) -> dict[str, str]:
    organization = Organization(name="Handling Org", slug=f"handling-org-{brand.id}")
    db.add(organization)
    await db.flush()
    user = User(
        email=f"handling-{brand.id}@example.com",
        username=f"handling_rep_{brand.id}",
        password_hash=get_password_hash("testpassword123"),
        active=True,
        email_verified=True,
        active_organization_id=organization.id,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.flush()
    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        )
    )
    db.add(
        BrandTerritorialGrant(
            brand_id=brand.id,
            organization_id=organization.id,
            country="RU",
            status=GrantStatus.active,
            source=GrantSource.invitation,
        )
    )
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


@pytest.mark.asyncio
async def test_ordinary_contributor_cannot_publish_density_or_handling_guidance(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "community")
    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Community ABS",
            "material_type": "ABS",
            "density": 1.04,
            "drying_required": True,
            "drying_temperature_c": 60,
            "drying_duration_hours": 4,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_NO_PERMISSION_EDIT_FILAMENT"


@pytest.mark.asyncio
async def test_ordinary_contributor_cannot_add_density_after_creating_product_shell(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "density-update")
    created = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Community PLA",
            "material_type": "PLA",
        },
    )
    assert created.status_code == 201, created.text

    response = await auth_client.patch(
        f"/api/v1/filaments/{created.json()['id']}",
        json={"density": 1.25},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_NO_PERMISSION_EDIT_FILAMENT"


@pytest.mark.asyncio
async def test_representative_can_publish_product_specific_handling_guidance(
    client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "representative")
    headers = await _representative_headers(db_session, brand)
    response = await client.post(
        "/api/v1/filaments/",
        headers=headers,
        json={
            "brand_id": brand.id,
            "name": "Representative ABS",
            "material_type": "ABS",
            "density": 1.05,
            "drying_required": True,
            "drying_temperature_c": 70,
            "drying_duration_hours": 6,
            "enclosure_requirement": "active",
            "chamber_temperature_c": 55,
            "bed_adhesives": ["Example build-plate adhesive"],
            "post_processing_chemicals": [
                {
                    "name": "Example solvent",
                    "purpose": "Surface finishing",
                    "hazardous": True,
                    "safety_note": "Follow the supplier SDS and use the specified controls.",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["density"] == 1.05
    assert payload["drying_required"] is True
    assert payload["drying_temperature_c"] == 70
    assert payload["drying_duration_hours"] == 6
    assert payload["enclosure_requirement"] == "active"
    assert payload["chamber_temperature_c"] == 55
    assert payload["bed_adhesives"] == ["Example build-plate adhesive"]
    assert payload["post_processing_chemicals"][0]["hazardous"] is True


@pytest.mark.asyncio
async def test_hazardous_chemical_requires_a_specific_safety_note(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "hazard-note")
    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Admin PETG",
            "material_type": "PETG",
            "post_processing_chemicals": [
                {"name": "Example solvent", "hazardous": True}
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_required_handling_parameters_are_not_accepted_without_values(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "handling-parameters")
    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Incomplete PC",
            "material_type": "PC",
            "drying_required": True,
            "enclosure_requirement": "active",
        },
    )
    assert response.status_code == 422
