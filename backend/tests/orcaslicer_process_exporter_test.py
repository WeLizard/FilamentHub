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


@pytest.mark.asyncio
async def test_machine_and_process_exports_preserve_unknown_json_shapes():
    unknown = {
        "future_scalar": 7.25,
        "future_vector": ["left", 2, False],
        "future_object": {"mode": "adaptive", "levels": [1, 3]},
        "future_nullable": None,
    }
    machine = PrinterProfile(
        id=2,
        name="Imported machine",
        slug="imported-machine",
        source="orcaslicer",
        is_official=False,
        active=True,
        orcaslicer_settings=unknown,
    )

    process_result = await print_profile_to_orca_json(_profile(unknown))
    machine_result = await printer_profile_to_orca_json(machine)

    for result in (process_result, machine_result):
        for key, value in unknown.items():
            assert result[key] == value
            assert type(result[key]) is type(value)
