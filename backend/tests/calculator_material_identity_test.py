"""Critical stable-ID boundaries for calculator material resolution."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.user import User
from app.schemas.calculator import CalculatorGcodeParseResponse
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
