import pytest

from app.models.print_profile import PrintProfile
from app.services.orcaslicer_machine_exporter import print_profile_to_orca_json


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


@pytest.mark.asyncio
async def test_explicit_template_visibility_is_preserved():
    result = await print_profile_to_orca_json(_profile({"instantiation": "false"}))
    assert result["instantiation"] == "false"
