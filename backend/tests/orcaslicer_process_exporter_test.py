from copy import deepcopy

import pytest

from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.services.orcaslicer_machine_exporter import (
    print_profile_to_orca_json,
    printer_profile_to_orca_json,
)


def _profile(settings: dict) -> PrintProfile:
    return PrintProfile(
        id=1,
        name="Imported process",
        slug="imported-process",
        source="orcaslicer",
        is_official=False,
        active=True,
        orcaslicer_settings=settings,
    )


@pytest.mark.asyncio
async def test_missing_instantiation_exports_as_visible_user_profile():
    result = await print_profile_to_orca_json(_profile({}))
    assert result["instantiation"] == "true"
    assert result["from"] == "user"


@pytest.mark.asyncio
async def test_explicit_template_visibility_is_preserved():
    result = await print_profile_to_orca_json(_profile({"instantiation": "false"}))
    assert result["instantiation"] == "false"


def _machine(settings: dict) -> PrinterProfile:
    return PrinterProfile(
        id=2,
        name="Imported machine",
        slug="imported-machine",
        source="orcaslicer",
        is_official=False,
        active=True,
        orcaslicer_settings=settings,
    )


@pytest.mark.asyncio
async def test_machine_and_process_exports_ship_unknown_transportable_shapes_verbatim():
    unknown = {
        "future_scalar": "7.25",
        "future_vector": ["left", "2", "0"],
        "future_grouped_vector": [["0", "0"], ["200", "200"]],
        "future_empty_vector": [],
    }

    process_result = await print_profile_to_orca_json(_profile(unknown))
    machine_result = await printer_profile_to_orca_json(_machine(unknown))

    for result in (process_result, machine_result):
        for key, value in unknown.items():
            assert result[key] == value
            assert type(result[key]) is type(value)


@pytest.mark.asyncio
async def test_machine_and_process_exports_withhold_shapes_orca_cannot_read():
    # Orca reads keys in sorted order and, on a bad array, abandons every
    # alphabetically later key — including `name` and `type`. Shipping an
    # unreviewed number, object or null therefore risks the whole profile, so
    # the export withholds it and the stored blob keeps it for the round trip.
    unknown = {
        "future_scalar": 7.25,
        "future_vector": ["left", 2, False],
        "future_object": {"mode": "adaptive", "levels": [1, 3]},
        "future_nullable": None,
    }
    process_profile = _profile(dict(unknown))
    machine_profile = _machine(dict(unknown))

    process_result = await print_profile_to_orca_json(process_profile)
    machine_result = await printer_profile_to_orca_json(machine_profile)

    for result, source in (
        (process_result, process_profile),
        (machine_result, machine_profile),
    ):
        for key, value in unknown.items():
            assert key not in result
            assert source.orcaslicer_settings[key] == value


@pytest.mark.asyncio
async def test_known_fields_are_normalized_for_both_profile_kinds():
    # The host Preset API returns native numbers, so a reverse-synced blob
    # carries them straight into the export unless the projection reshapes them.
    process_result = await print_profile_to_orca_json(
        _profile(
            {
                "outer_wall_speed": [200],
                "travel_speed": 300.5,
                "enable_mixed_color_sublayer": True,
            }
        )
    )
    machine_result = await printer_profile_to_orca_json(
        _machine(
            {
                "nozzle_diameter": [0.4],
                "retraction_length": 0.8,
                "wipe": [True],
                "is_custom_defined": False,
            }
        )
    )

    assert process_result["outer_wall_speed"] == ["200"]
    assert process_result["travel_speed"] == ["300.5"]
    assert process_result["enable_mixed_color_sublayer"] == "1"
    assert machine_result["nozzle_diameter"] == ["0.4"]
    assert machine_result["retraction_length"] == ["0.8"]
    assert machine_result["wipe"] == ["1"]
    assert machine_result["is_custom_defined"] == "0"


@pytest.mark.asyncio
async def test_exports_never_mutate_the_stored_settings_blob():
    stored = {"nozzle_diameter": [0.4], "future_object": {"levels": [1, 3]}}
    machine_profile = _machine(stored)
    snapshot = deepcopy(stored)

    await printer_profile_to_orca_json(machine_profile)
    await printer_profile_to_orca_json(machine_profile)

    assert machine_profile.orcaslicer_settings == snapshot
