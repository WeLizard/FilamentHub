"""Tests that tested-on PresetPrinter links do not become hard material filters."""

from copy import deepcopy

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.print_profile import PrintProfile
from app.models.printer import Printer
from app.services.orca_transport import merge_orca_roundtrip_settings
from app.services.orcaslicer_exporter import preset_to_orcaslicer_json
from app.services.orcaslicer_machine_exporter import print_profile_to_orca_json
from app.services.preset_import_evidence import new_import_evidence
from app.services.preset_publication import apply_public_orca_identity


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
async def test_tested_on_links_remain_in_catalog_but_do_not_restrict_export(
    client: AsyncClient, db_session: AsyncSession,
):
    preset = await _seed_preset(db_session)
    p1 = await _add_printer(db_session, name="Bambu Lab P2S", slug="bbl-p2s", source="system")
    p2 = await _add_printer(db_session, name="Voron 2.4 350", slug="voron-24-350", source="system")
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=p1.id, is_primary=True))
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=p2.id))
    await db_session.commit()

    # Filtering/discovery still uses tested-on evidence, and both links survive
    # the public API projection used by the website's preset lists.
    response = await client.get("/api/v1/presets/", params={"printer_id": p1.id})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["id"] == preset.id
    assert {printer["name"] for printer in item["printers"]} == {
        "Bambu Lab P2S", "Voron 2.4 350",
    }
    detail = await client.get(f"/api/v1/presets/{preset.id}")
    assert detail.status_code == 200
    assert {printer["id"] for printer in detail.json()["printers"]} == {p1.id, p2.id}
    export_filament = Filament(id=preset.filament_id, name="Compat PLA", material_type="PLA", diameter=1.75)
    profile = await preset_to_orcaslicer_json(preset, export_filament, db=db_session)
    assert "compatible_printers" not in profile
    assert "compatible_printers_condition" not in profile


@pytest.mark.asyncio
@pytest.mark.parametrize("custom_printer", [False, True])
async def test_unscoped_without_system_links_is_universal(db_session: AsyncSession, custom_printer: bool):
    preset = await _seed_preset(db_session)
    if custom_printer:
        custom = await _add_printer(db_session, name="My Custom Rig", slug="custom-rig", source="user")
        db_session.add(PresetPrinter(preset_id=preset.id, printer_id=custom.id))
    await db_session.commit()
    export_filament = Filament(id=preset.filament_id, name="Compat PLA", material_type="PLA", diameter=1.75)
    profile = await preset_to_orcaslicer_json(preset, export_filament, db=db_session)
    assert "compatible_printers" not in profile
    assert "compatible_printers_condition" not in profile


@pytest.mark.asyncio
async def test_legacy_restrictions_stay_in_source_evidence_but_never_in_managed_export(db_session: AsyncSession):
    preset = await _seed_preset(db_session)
    preset.orcaslicer_settings = {
        "compatible_printers": ["Voron 2.4 350 0.4 nozzle"],
        "compatible_printers_condition": 'printer_model=="Voron 2.4 350"',
        "filament_max_volumetric_speed": ["15"],
    }
    preset.import_evidence = new_import_evidence(
        settings=preset.orcaslicer_settings, name=preset.name,
        source="orcaslicer", external_id="private-import",
    )
    original = deepcopy(preset.orcaslicer_settings)
    evidence = deepcopy(preset.import_evidence)
    await db_session.commit()

    export_filament = Filament(id=preset.filament_id, name="Compat PLA", material_type="PLA", diameter=1.75)
    profile = await preset_to_orcaslicer_json(preset, export_filament, db=db_session)

    assert "compatible_printers" not in profile
    assert "compatible_printers_condition" not in profile
    assert profile["filament_max_volumetric_speed"] == ["15"]
    assert preset.orcaslicer_settings == original
    assert preset.import_evidence == evidence

    # A pinned historical version is subject to the same export policy.
    overridden = await preset_to_orcaslicer_json(
        preset, export_filament, db=db_session, settings_override=original,
    )
    assert "compatible_printers" not in overridden
    assert "compatible_printers_condition" not in overridden
    returned = merge_orca_roundtrip_settings(original, profile, "filament")
    for key in ("compatible_printers", "compatible_printers_condition"):
        assert returned[key] == original[key]

    apply_public_orca_identity(preset)
    assert "compatible_printers" not in preset.orcaslicer_settings
    assert "compatible_printers_condition" not in preset.orcaslicer_settings
    assert preset.import_evidence == evidence
    assert preset.import_evidence["original"]["settings"] == original


@pytest.mark.asyncio
async def test_process_printer_compatibility_still_roundtrips():
    original = {
        "compatible_printers": ["Bambu Lab P2S 0.4 nozzle"],
        "compatible_printers_condition": 'printer_model=="Bambu Lab P2S"',
    }
    profile = PrintProfile(
        id=1, name="Process", slug="process", source="orcaslicer",
        orcaslicer_settings=deepcopy(original),
    )
    exported = await print_profile_to_orca_json(profile)
    for key, value in original.items():
        assert exported[key] == value
    assert profile.orcaslicer_settings == original
    returned = merge_orca_roundtrip_settings(original, exported, "process")
    for key, value in original.items():
        assert returned[key] == value
    # A real process-side removal must not be mistaken for the filament policy.
    assert merge_orca_roundtrip_settings(original, {}, "process") == {}
