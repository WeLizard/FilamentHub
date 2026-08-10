"""Critical stable-ID boundaries for calculator material resolution."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.user import User
from app.schemas.calculator import CalculatorFhubIdentity, CalculatorGcodeParseResponse
from app.services.calculator_material_identity_service import (
    resolve_calculator_material_identities,
)


def _parsed(stable_id: str, *, name: str = "Misleading profile name") -> CalculatorGcodeParseResponse:
    return CalculatorGcodeParseResponse(
        file_name="job.gcode",
        file_size_bytes=100,
        materials=[
            {
                "tool_index": 0,
                "name": name,
                "slicer_filament_id": stable_id,
                "weight_g": 10,
            }
        ],
    )


async def _filament(db: AsyncSession, brand: Brand, *, name: str, slug: str) -> Filament:
    filament = Filament(
        brand_id=brand.id,
        name=name,
        slug=slug,
        material_type="PLA",
        diameter=1.75,
    )
    db.add(filament)
    await db.flush()
    return filament


@pytest.mark.asyncio
async def test_filamenthub_gcode_id_resolves_catalog_material_before_name(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Stable ID Brand", slug="stable-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Actual catalog PLA",
        slug="actual-catalog-pla",
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _parsed(f"FHUB_F_{filament.id:06d}"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.source == "filamenthub_filament_id"
    assert resolution.filament_id == filament.id


@pytest.mark.asyncio
async def test_namespaced_managed_preset_resolves_before_orca_family_id(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Managed ID Brand", slug="managed-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Exact managed PETG",
        slug="exact-managed-petg",
    )
    preset = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        name="Exact managed preset",
        extruder_temp=240,
        bed_temp=80,
        is_official=False,
        active=True,
    )
    db_session.add(preset)
    await db_session.flush()
    parsed = _parsed("OGFG99")
    parsed = parsed.model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=preset.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        parsed,
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.source == "filamenthub_preset_id"
    assert resolution.preset_id == preset.id
    assert resolution.filament_id == filament.id
    assert resolved.fhub_identities[0].entity_id == preset.id


@pytest.mark.asyncio
async def test_private_foreign_preset_identity_is_not_trusted(
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    brand = Brand(name="Private ID Brand", slug="private-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Private managed PETG",
        slug="private-managed-petg",
    )
    preset = Preset(
        filament_id=filament.id,
        user_id=admin_user.id,
        name="Someone else's draft",
        extruder_temp=240,
        bed_temp=80,
        is_official=False,
        active=False,
    )
    db_session.add(preset)
    await db_session.flush()
    parsed = _parsed("OGFG99").model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=preset.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        parsed,
        user_id=auth_user.id,
    )

    assert resolved.fhub_identities == []
    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "unresolved"
    assert resolution.stable_id == "OGFG99"


@pytest.mark.asyncio
async def test_legacy_filamenthub_gcode_id_remains_readable(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    """Old G-code remains usable after separating preset and material IDs."""
    brand = Brand(name="Legacy ID Brand", slug="legacy-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Legacy catalog PLA",
        slug="legacy-catalog-pla",
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _parsed(f"FHUB{filament.id:06d}"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.source == "filamenthub_filament_id"
    assert resolution.filament_id == filament.id


@pytest.mark.asyncio
async def test_conflicting_exact_user_preset_mappings_remain_ambiguous(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Provider ID Brand", slug="provider-id-brand")
    db_session.add(brand)
    await db_session.flush()
    first = await _filament(db_session, brand, name="First PLA", slug="first-provider-pla")
    second = await _filament(db_session, brand, name="Second PLA", slug="second-provider-pla")
    for index, filament in enumerate((first, second), start=1):
        db_session.add(
            Preset(
                filament_id=filament.id,
                user_id=auth_user.id,
                name=f"Provider preset {index}",
                extruder_temp=210,
                bed_temp=60,
                is_official=False,
                active=True,
                orcaslicer_settings={"filament_id": "VENDOR-MATERIAL-42"},
            )
        )
    await db_session.flush()

    resolved = await resolve_calculator_material_identities(
        db_session,
        _parsed("VENDOR-MATERIAL-42"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "ambiguous"
    assert resolution.source == "user_preset_filament_id"
    assert resolution.filament_id is None
    assert resolution.candidate_filament_ids == [first.id, second.id]
