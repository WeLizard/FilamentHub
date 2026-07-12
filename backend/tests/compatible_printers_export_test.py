"""Tests for compatible_printers_condition export from PresetPrinter links.

A filament preset must carry the printers it was authored for as an Orca
compatible_printers_condition (by canonical printer_model), and stay open
(compatible with all) when it has no usable links.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.services.orcaslicer_exporter import (
    build_compatible_printers_condition,
    preset_to_orcaslicer_json,
)


async def _seed_preset(db: AsyncSession) -> Preset:
    brand = Brand(name="Compat Brand", slug="compat-brand", active=True)
    db.add(brand)
    await db.flush()

    filament = Filament(
        brand_id=brand.id,
        name="Compat PLA",
        slug="compat-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.flush()

    preset = Preset(
        filament_id=filament.id,
        name="Compat Preset",
        is_official=True,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db.add(preset)
    await db.flush()
    return preset


async def _add_printer(db: AsyncSession, *, name: str, slug: str, source: str) -> Printer:
    printer = Printer(name=name, manufacturer="Vendor", model=name, slug=slug, source=source)
    db.add(printer)
    await db.flush()
    return printer


@pytest.mark.asyncio
async def test_condition_from_system_printers(db_session: AsyncSession):
    preset = await _seed_preset(db_session)
    p1 = await _add_printer(db_session, name="Bambu Lab X1 Carbon", slug="bbl-x1c", source="system")
    p2 = await _add_printer(db_session, name="Voron 2.4 350", slug="voron-24-350", source="system")
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=p1.id, is_primary=True))
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=p2.id))
    await db_session.commit()

    condition = await build_compatible_printers_condition(preset, db_session)
    assert condition is not None
    assert 'printer_model=="Bambu Lab X1 Carbon"' in condition
    assert 'printer_model=="Voron 2.4 350"' in condition
    assert " or " in condition


@pytest.mark.asyncio
async def test_no_links_leaves_open(db_session: AsyncSession):
    preset = await _seed_preset(db_session)
    await db_session.commit()
    assert await build_compatible_printers_condition(preset, db_session) is None


@pytest.mark.asyncio
async def test_non_system_printer_does_not_narrow(db_session: AsyncSession):
    preset = await _seed_preset(db_session)
    custom = await _add_printer(db_session, name="My Custom Rig", slug="custom-rig", source="user")
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=custom.id))
    await db_session.commit()
    assert await build_compatible_printers_condition(preset, db_session) is None


@pytest.mark.asyncio
async def test_export_sets_condition_and_empty_list(db_session: AsyncSession):
    preset = await _seed_preset(db_session)
    p1 = await _add_printer(db_session, name="Bambu Lab X1 Carbon", slug="bbl-x1c", source="system")
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=p1.id, is_primary=True))
    await db_session.commit()

    # Transient filament (no lazy brand load); the preset stays persistent for the link query.
    export_filament = Filament(id=preset.filament_id, name="Compat PLA", material_type="PLA", diameter=1.75)
    profile = await preset_to_orcaslicer_json(preset, export_filament, db=db_session)
    assert profile["compatible_printers"] == []
    assert profile["compatible_printers_condition"] == 'printer_model=="Bambu Lab X1 Carbon"'
