"""Identity safeguards for refreshing the canonical Orca bundle."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.printer_profile import PrinterProfile
from app.schemas.orca_bundle import OrcaMachinePreset, OrcaProcessPreset
from app.services.orca_bundle_importer import (
    OrcaBundleImporter,
    _renamed_aliases,
    _resolve_effective_process_preset,
)


def test_orca_string_false_is_parsed_as_a_common_machine_profile():
    preset = OrcaMachinePreset.model_validate(
        {
            "name": "Lulzbot Taz Pro Common",
            "type": "machine",
            "instantiation": "false",
            "printer_model": "Lulzbot Taz Pro Common",
        }
    )

    assert preset.instantiation is False


def test_process_compatibility_is_inherited_without_flattening_raw_child():
    parent = OrcaProcessPreset.model_validate(
        {
            "type": "process",
            "name": "0.20mm Standard @Voron",
            "compatible_printers": ["Voron 2.4 350 0.4 nozzle"],
            "compatible_printers_condition": "printer_model==\"Voron 2.4 350\"",
            "layer_height": "0.20",
        }
    )
    child = OrcaProcessPreset.model_validate(
        {
            "type": "process",
            "name": "0.20mm Standard @Voron 2.4 350",
            "inherits": parent.name,
            "wall_loops": "3",
        }
    )

    effective = _resolve_effective_process_preset(
        child.name,
        presets={parent.name: parent, child.name: child},
        cache={},
    )

    assert effective.parameters["compatible_printers"] == [
        "Voron 2.4 350 0.4 nozzle"
    ]
    assert effective.parameters["layer_height"] == "0.20"
    assert effective.parameters["wall_loops"] == "3"
    assert effective.compatible_printers_condition == (
        'printer_model=="Voron 2.4 350"'
    )
    assert "compatible_printers" not in child.parameters


@pytest.mark.asyncio
async def test_bundle_materialises_exact_process_to_machine_link(
    db_session: AsyncSession,
):
    machine = PrinterProfile(
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-2-4-350-04-exact-bundle-link",
        vendor="Voron",
        source="system",
        is_official=True,
        active=True,
    )
    process = PrintProfile(
        name="0.20mm Standard @Voron",
        slug="020-standard-voron-exact-bundle-link",
        vendor="Voron",
        source="system",
        is_official=True,
        active=True,
        compatible_printers=[machine.name],
    )
    db_session.add_all([machine, process])
    await db_session.flush()

    importer = OrcaBundleImporter()
    importer._printer_profile_cache[("Voron", machine.name)] = machine
    await importer._sync_vendor_configuration_links(
        db=db_session,
        vendor_name="Voron",
        profiles=[process],
    )

    links = list(
        (
            await db_session.execute(
                select(PrintProfileConfigurationLink).where(
                    PrintProfileConfigurationLink.print_profile_id == process.id
                )
            )
        ).scalars()
    )
    assert [link.printer_profile_id for link in links] == [machine.id]
    assert process.configuration_links_resolved is True


@pytest.mark.asyncio
async def test_bundle_setting_id_alone_never_renames_a_profile(
    db_session: AsyncSession,
):
    existing = PrinterProfile(
        name="Workshop A1 mini",
        slug="workshop-a1-mini-canonical",
        vendor="BambuLab",
        setting_id="Bambu Lab A1 mini 0.4 nozzle",
        source="system",
        is_official=True,
        active=True,
    )
    db_session.add(existing)
    await db_session.commit()

    importer = OrcaBundleImporter()
    match = await importer._find_printer_profile(
        db=db_session,
        vendor_name="BambuLab",
        setting_id="Bambu Lab A1 mini 0.4 nozzle",
        name="Office A1 mini",
        renamed_from=set(),
    )

    assert match is None


@pytest.mark.asyncio
async def test_bundle_explicit_rename_alias_preserves_canonical_identity(
    db_session: AsyncSession,
):
    existing = PrinterProfile(
        name="Bambu Lab A1 mini 0.4 nozzle",
        slug="bambu-a1-mini-canonical-alias",
        vendor="BambuLab",
        setting_id="BBL-A1M-04",
        source="system",
        is_official=True,
        active=True,
    )
    db_session.add(existing)
    await db_session.commit()

    importer = OrcaBundleImporter()
    match = await importer._find_printer_profile(
        db=db_session,
        vendor_name="BambuLab",
        setting_id="BBL-A1M-04-v2",
        name="Bambu Lab A1 mini 0.4 nozzle v2",
        renamed_from=_renamed_aliases("Bambu Lab A1 mini 0.4 nozzle.json"),
    )

    assert match is not None
    assert match.id == existing.id
