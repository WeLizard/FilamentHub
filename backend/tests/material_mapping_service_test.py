"""Tests for get_material_preset — the source of the exported `inherits` parent.

The invariant that matters for Orca: the returned name must be non-empty and
resolvable to a system preset, otherwise the exported filament profile either
loads without inheriting a base (empty inherits) or is skipped entirely
(non-empty but unresolvable). The backend is the last line of defence for the
non-plugin path (a user who downloads the JSON and imports it by hand).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_mapping import MaterialMapping, MaterialMappingPriority
from app.services.material_mapping_service import get_material_preset


@pytest.mark.asyncio
async def test_known_base_type_maps_to_system_generic(db_session: AsyncSession):
    assert await get_material_preset("PLA", db_session) == "Generic PLA @System"


@pytest.mark.asyncio
async def test_unknown_type_falls_back_to_common(db_session: AsyncSession):
    assert await get_material_preset("NOPE-9000", db_session) == "fdm_filament_common"


@pytest.mark.asyncio
async def test_active_mapping_wins(db_session: AsyncSession):
    db_session.add(
        MaterialMapping(
            material_type="PLA",
            orcaslicer_preset="Bambu PLA Basic @BBL X1C",
            priority=MaterialMappingPriority.BRAND,
            active=True,
        )
    )
    await db_session.commit()

    assert await get_material_preset("PLA", db_session) == "Bambu PLA Basic @BBL X1C"


@pytest.mark.asyncio
async def test_empty_mapping_is_ignored_and_falls_back(db_session: AsyncSession):
    # An admin-created mapping with a blank preset must not leak an empty inherits;
    # it is ignored and the known system generic is used instead.
    db_session.add(
        MaterialMapping(
            material_type="PLA",
            orcaslicer_preset="   ",
            priority=MaterialMappingPriority.MANUAL,
            active=True,
        )
    )
    await db_session.commit()

    assert await get_material_preset("PLA", db_session) == "Generic PLA @System"


@pytest.mark.asyncio
async def test_result_is_always_non_empty(db_session: AsyncSession):
    for material in ("PLA", "PETG-CF", "PA6", "totally-unknown", ""):
        result = await get_material_preset(material, db_session, log_unknown=False)
        assert result and result.strip(), f"empty inherits for {material!r}"
