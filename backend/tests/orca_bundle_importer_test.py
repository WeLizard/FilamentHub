"""Identity safeguards for refreshing the canonical Orca bundle."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.schemas.orca_bundle import OrcaMachineModel, OrcaMachinePreset, OrcaProcessPreset
from app.services.orca_bundle_importer import (
    OrcaBundleImporter,
    _renamed_aliases,
    _resolve_effective_process_preset,
)


@pytest.mark.asyncio
async def test_bambu_identity_repairs_legacy_display_without_duplicate(
    db_session: AsyncSession,
):
    legacy = Printer(
        name="BambuLab Bambu Lab P2S",
        manufacturer="BambuLab",
        model="Bambu Lab P2S",
        slug="legacy-bambulab-p2s",
        vendor="BambuLab",
        source="system",
    )
    db_session.add(legacy)
    await db_session.flush()

    importer = OrcaBundleImporter()
    machine = OrcaMachineModel(
        type="machine_model",
        name="Bambu Lab P2S",
        model_id="P2S",
    )
    resolved = await importer._upsert_printer(
        db=db_session,
        vendor_name="BambuLab",
        machine_model=machine,
    )

    assert resolved.id == legacy.id
    assert resolved.name == "Bambu Lab P2S"
    assert resolved.manufacturer == "Bambu Lab"
    assert resolved.model == "P2S"


@pytest.mark.asyncio
async def test_importer_does_not_choose_ambiguous_external_model_id(
    db_session: AsyncSession,
):
    db_session.add_all(
        [
            Printer(
                name="Vendor Model A",
                manufacturer="Vendor",
                model="Model A",
                slug="vendor-model-a-identity",
                vendor="Vendor",
                model_id="shared-id",
                source="system",
            ),
            Printer(
                name="Vendor Model B",
                manufacturer="Vendor",
                model="Model B",
                slug="vendor-model-b-identity",
                vendor="Vendor",
                model_id="shared-id",
                source="system",
            ),
        ]
    )
    await db_session.flush()

    importer = OrcaBundleImporter()
    assert await importer._find_printer(
        db=db_session,
        vendor_name="Vendor",
        name="Vendor Unseen Model",
    ) is None


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


@pytest.mark.asyncio
async def test_shared_model_id_does_not_overwrite_previous_bundle_model(db_session):
    importer = OrcaBundleImporter()
    first = await importer._upsert_printer(
        db=db_session, vendor_name="Prusa",
        machine_model=OrcaMachineModel(type="machine_model", name="Prusa MINI", model_id="MINI"),
    )
    await db_session.flush()
    second = await importer._upsert_printer(
        db=db_session, vendor_name="Prusa",
        machine_model=OrcaMachineModel(type="machine_model", name="Prusa MINI IS", model_id="MINI"),
    )
    await db_session.flush()
    assert first.id != second.id
    assert first.name == "Prusa MINI"
    assert second.name == "Prusa MINI IS"


@pytest.mark.asyncio
async def test_canonical_row_wins_over_legacy_and_custom_rows_are_untouched(db_session):
    rows = [
        Printer(name=name, manufacturer="BambuLab", model="P2S", vendor="BambuLab",
                source=source, slug=f"bambu-identity-{index}")
        for index, (name, source) in enumerate([
            ("Bambu Lab P2S", "system"),
            ("BambuLab Bambu Lab P2S", "system"),
            ("Bambu Lab P2S", "user"),
        ])
    ]
    db_session.add_all(rows)
    await db_session.flush()
    importer = OrcaBundleImporter()
    for _ in range(2):
        refreshed = await importer._upsert_printer(
            db=db_session, vendor_name="BambuLab",
            machine_model=OrcaMachineModel(type="machine_model", name="Bambu Lab P2S"),
        )
        assert refreshed.id == rows[0].id
    assert rows[1].name == "BambuLab Bambu Lab P2S"
    assert rows[2].source == "user"


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


@pytest.mark.asyncio
async def test_bundle_process_links_do_not_guess_from_nozzle_suffix(db_session):
    model = Printer(name="Bambu Lab P2S", model="P2S", manufacturer="Bambu Lab",
                    source="system", vendor="BambuLab", slug="bundle-no-guess-p2s")
    process = PrintProfile(name="Process", slug="bundle-no-guess-process",
                           printer_links=[], filament_links=[])
    db_session.add_all([model, process])
    await db_session.flush()
    await OrcaBundleImporter()._sync_print_profile_links(
        db=db_session, profile=process, vendor_name="BambuLab",
        compatible_printers=["Bambu Lab P2S 0.4 nozzle"],
        compatible_printers_condition=None, compatible_filaments=None,
    )
    assert len(process.printer_links) == 1
    assert process.printer_links[0].printer_id is None


@pytest.mark.asyncio
async def test_bundle_inheritance_never_selects_first_ambiguous_parent(db_session):
    parents = [PrinterProfile(name="Common", slug=f"bundle-parent-{index}",
                              vendor=vendor, source="system",
                              orcaslicer_settings={"printer_model": vendor})
               for index, vendor in enumerate(["Vendor A", "Vendor B"])]
    child = PrinterProfile(name="Child", slug="bundle-child", vendor="Other",
                           source="system", orcaslicer_settings={"inherits": "Common"})
    db_session.add_all([*parents, child])
    await db_session.flush()
    settings = await OrcaBundleImporter()._resolve_inheritance(db_session, child)
    assert settings == {"inherits": "Common"}


@pytest.mark.asyncio
async def test_first_bundle_import_resolves_process_after_exact_machine_exists(db_session, tmp_path):
    vendor_dir = tmp_path / "BBL"
    (vendor_dir / "machine").mkdir(parents=True)
    (vendor_dir / "process").mkdir()
    fixtures = {
        "BBL.json": {"name": "Bambulab", "version": "1.0.0",
                     "machine_model_list": [{"name": "Bambu Lab P2S", "sub_path": "machine/P2S.json"}],
                     "process_list": [{"name": "Standard P2S", "sub_path": "process/standard.json"}]},
        "BBL/machine/P2S.json": {"type": "machine_model", "name": "Bambu Lab P2S"},
        "BBL/machine/custom.json": {"type": "machine", "name": "Exact custom-looking name",
                                    "printer_model": "Bambu Lab P2S", "instantiation": "true"},
        "BBL/process/standard.json": {"type": "process", "name": "Standard P2S",
                                      "compatible_printers": ["Exact custom-looking name"],
                                      "compatible_printers_condition": 'printer_model=="Bambu Lab P2S"'},
    }
    for relative, payload in fixtures.items():
        (tmp_path / relative).write_text(json.dumps(payload), encoding="utf-8")
    for _ in range(2):
        await OrcaBundleImporter(root_path=tmp_path).import_all(db_session)
        model = await db_session.scalar(select(Printer).where(Printer.name == "Bambu Lab P2S"))
        process = await db_session.scalar(select(PrintProfile).where(PrintProfile.name == "Standard P2S"))
        links = await process.awaitable_attrs.printer_links
        assert [link.printer_id for link in links if link.relation_type == "explicit"] == [model.id]
        assert process.compatible_printers == ["Exact custom-looking name"]
        assert process.orcaslicer_settings["compatible_printers_condition"] == 'printer_model=="Bambu Lab P2S"'
