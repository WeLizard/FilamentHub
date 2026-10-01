"""A preset exported to OrcaSlicer loads on any printer of any user.

Presets 185/199/191 on production were saved from copies of Bambu profiles.
The stored vendor parent restricted them to Bambu X1 printers, and a receiver
without the Bambu vendor could not resolve it at all.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.orca_sync import _declared_material_type
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.schemas.orca_sync import OrcaFilamentPresetPayload
from app.services.orca_transport import merge_orca_roundtrip_settings
from app.services.orcaslicer_exporter import preset_to_orcaslicer_json

VENDOR_PARENT = "Bambu PLA Basic @BBL X1"


async def _published_preset(
    db: AsyncSession, material_type: str, settings: dict
) -> tuple[Preset, Filament]:
    brand = Brand(name="Parent Brand", slug="parent-brand", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand=brand,
        name="Parent Filament",
        slug="parent-filament",
        material_type=material_type,
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.flush()
    preset = Preset(
        filament_id=filament.id,
        name="Parent Preset",
        extruder_temp=240.0,
        bed_temp=80.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
        orcaslicer_settings=settings,
    )
    db.add(preset)
    await db.flush()
    return preset, filament


@pytest.mark.asyncio
async def test_a_copied_vendor_profile_exports_on_the_universal_material_parent(
    db_session: AsyncSession,
):
    stored = {
        "inherits": VENDOR_PARENT,
        "filament_type": ["PLA"],
        "pressure_advance": ["0.02"],
        "compatible_printers": ["Bambu Lab X1 0.4 nozzle"],
    }
    preset, filament = await _published_preset(db_session, "PETG", dict(stored))

    profile = await preset_to_orcaslicer_json(preset, filament)

    assert profile["inherits"] == "Generic PETG @System"
    assert profile["filament_type"] == ["PETG"]
    assert profile["compatible_printers"] == []
    assert profile["compatible_printers_condition"] == ""
    assert profile["pressure_advance"] == ["0.02"]
    assert preset.orcaslicer_settings == stored


@pytest.mark.asyncio
async def test_a_plus_variant_inherits_its_base_material(db_session: AsyncSession):
    preset, filament = await _published_preset(
        db_session, "PETG+", {"inherits": "Generic PETG @K2 Pro-all"}
    )

    profile = await preset_to_orcaslicer_json(preset, filament)

    assert profile["inherits"] == "Generic PETG @System"


def test_a_returned_export_never_turns_printer_compatibility_into_an_edit():
    stored = {"compatible_printers": ["Bambu Lab X1 0.4 nozzle"], "pressure_advance": ["0.02"]}
    returned = {
        "compatible_printers": ["Some Printer"],
        "compatible_printers_condition": 'printer_model=="Some Printer"',
        "pressure_advance": ["0.03"],
    }

    merged = merge_orca_roundtrip_settings(stored, returned, "filament")

    assert merged["compatible_printers"] == ["Bambu Lab X1 0.4 nozzle"]
    assert "compatible_printers_condition" not in merged
    assert merged["pressure_advance"] == ["0.03"]


def test_the_authors_material_wins_over_the_parent_name():
    copied_and_switched = OrcaFilamentPresetPayload(
        name="PETG Gold [fh]",
        inherits=VENDOR_PARENT,
        orcaslicer_settings={"filament_type": ["PETG"]},
    )
    untouched_copy = OrcaFilamentPresetPayload(
        name="PLA copy [fh]", inherits=VENDOR_PARENT, orcaslicer_settings={}
    )

    assert _declared_material_type(copied_and_switched) == "PETG"
    assert _declared_material_type(untouched_copy) == "PLA"
