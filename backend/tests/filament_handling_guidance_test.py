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


async def _representative_headers(
    db: AsyncSession,
    brand: Brand,
    *,
    label: str = "representative",
    country: str | None = "RU",
) -> dict[str, str]:
    organization = Organization(
        name=f"Handling Org {label}", slug=f"handling-org-{brand.id}-{label}"
    )
    db.add(organization)
    await db.flush()
    user = User(
        email=f"handling-{brand.id}-{label}@example.com",
        username=f"handling_rep_{brand.id}_{label}",
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
            country=country,
            status=GrantStatus.active,
            source=GrantSource.invitation,
            edit_all_filaments_common=country is None,
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
            "storage_airtight_required": True,
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
    assert created.json()["storage_airtight_required"] is None
    assert created.json()["technical_data_last_verified_by"] is None

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
            "storage_temperature_min_c": 10,
            "storage_temperature_max_c": 30,
            "storage_relative_humidity_max_percent": 30,
            "storage_relative_humidity_target_percent": 20,
            "storage_airtight_required": True,
            "storage_desiccant_recommended": True,
            "storage_light_protection_required": True,
            "storage_after_opening_guidance": "Reseal with fresh desiccant after use.",
            "unopened_shelf_life_months": 24,
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
            "spool_weight": 1000,
            "empty_spool_weight_g": 220,
            "spool_outer_diameter_mm": 200,
            "spool_width_mm": 70,
            "spool_core_diameter_mm": 52,
            "packaged_gross_weight_g": 1300,
            "recommended_nozzle_temp_min": 230,
            "recommended_nozzle_temp_max": 260,
            "technical_data_source_ref": "TDS-ABS-2026",
            "technical_data_version": "3.2",
            "technical_data_effective_date": "2026-08-01",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["density"] == 1.05
    assert payload["drying_required"] is True
    assert payload["drying_temperature_c"] == 70
    assert payload["drying_duration_hours"] == 6
    assert payload["storage_temperature_min_c"] == 10
    assert payload["storage_temperature_max_c"] == 30
    assert payload["storage_relative_humidity_max_percent"] == 30
    assert payload["storage_relative_humidity_target_percent"] == 20
    assert payload["storage_airtight_required"] is True
    assert payload["storage_desiccant_recommended"] is True
    assert payload["storage_light_protection_required"] is True
    assert payload["storage_after_opening_guidance"] == "Reseal with fresh desiccant after use."
    assert payload["unopened_shelf_life_months"] == 24
    assert payload["enclosure_requirement"] == "active"
    assert payload["chamber_temperature_c"] == 55
    assert payload["bed_adhesives"] == ["Example build-plate adhesive"]
    assert payload["post_processing_chemicals"][0]["hazardous"] is True
    assert payload["spool_outer_diameter_mm"] == 200
    assert payload["spool_width_mm"] == 70
    assert payload["spool_core_diameter_mm"] == 52
    assert payload["packaged_gross_weight_g"] == 1300
    assert payload["technical_data_source_ref"] == "TDS-ABS-2026"
    assert payload["technical_data_version"] == "3.2"
    assert payload["technical_data_effective_date"] == "2026-08-01"
    assert payload["technical_data_last_verified_by"] == "manufacturer_representative"
    assert payload["technical_data_last_verified_at"] is not None

    public_detail = await client.get(f"/api/v1/filaments/{payload['id']}")
    assert public_detail.status_code == 200
    assert public_detail.json()["storage_relative_humidity_target_percent"] == 20
    assert public_detail.json()["technical_data_source_ref"] == "TDS-ABS-2026"

    public_list = await client.get(f"/api/v1/filaments/?brand_id={brand.id}")
    assert public_list.status_code == 200
    listed = next(item for item in public_list.json()["items"] if item["id"] == payload["id"])
    assert listed["spool_outer_diameter_mm"] == 200
    assert listed["technical_data_last_verified_by"] == "manufacturer_representative"


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
            "post_processing_chemicals": [{"name": "Example solvent", "hazardous": True}],
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "technical_data",
    [
        {
            "drying_required": False,
            "drying_temperature_c": 60,
            "drying_duration_hours": 4,
        },
        {"drying_temperature_c": 60},
        {"storage_temperature_min_c": 10},
        {"storage_temperature_min_c": 30, "storage_temperature_max_c": 10},
        {
            "storage_relative_humidity_max_percent": 20,
            "storage_relative_humidity_target_percent": 30,
        },
        {"spool_outer_diameter_mm": 200, "spool_core_diameter_mm": 220},
        {
            "spool_weight": 1000,
            "empty_spool_weight_g": 200,
            "packaged_gross_weight_g": 1100,
        },
        {"recommended_nozzle_temp_min": 260, "recommended_nozzle_temp_max": 230},
    ],
)
async def test_contradictory_technical_declarations_are_rejected(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    technical_data: dict[str, object],
):
    brand = await _brand(db_session, "invalid-technical-data")
    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Contradictory declaration",
            "material_type": "PA",
            **technical_data,
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_validates_the_resulting_technical_state(
    admin_client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "merged-validation")
    created = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Stored PA",
            "material_type": "PA",
            "storage_temperature_min_c": 10,
            "storage_temperature_max_c": 30,
        },
    )
    assert created.status_code == 201, created.text

    response = await admin_client.patch(
        f"/api/v1/filaments/{created.json()['id']}",
        json={"storage_temperature_min_c": 31},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_regional_representative_fills_only_missing_technical_data(
    admin_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
):
    brand = await _brand(db_session, "regional-gap")
    created = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Regional PA",
            "material_type": "PA",
            "storage_relative_humidity_max_percent": 35,
        },
    )
    assert created.status_code == 201, created.text

    await _representative_headers(
        db_session,
        brand,
        label="global",
        country=None,
    )
    regional_headers = await _representative_headers(
        db_session,
        brand,
        label="regional",
        country="RU",
    )

    filled = await client.patch(
        f"/api/v1/filaments/{created.json()['id']}",
        headers=regional_headers,
        json={
            "storage_relative_humidity_max_percent": 20,
            "storage_airtight_required": False,
        },
    )
    assert filled.status_code == 200, filled.text
    assert filled.json()["storage_relative_humidity_max_percent"] == 35
    assert filled.json()["storage_airtight_required"] is False
    assert filled.json()["technical_data_last_verified_by"] == "manufacturer_representative"

    overwrite = await client.patch(
        f"/api/v1/filaments/{created.json()['id']}",
        headers=regional_headers,
        json={"storage_airtight_required": True},
    )
    assert overwrite.status_code == 403
