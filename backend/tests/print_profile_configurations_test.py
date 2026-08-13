"""Exact process-profile/configuration links and their account boundary."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.services.print_profile_configuration_service import replace_configuration_links

from .conftest import accepted_legal


@pytest.mark.asyncio
async def test_process_targeting_factory_parent_is_projected_to_user_machine_child(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    parent = PrinterProfile(
        name="Voron 2.4 350 0.4 nozzle",
        slug="voron-parent-projection",
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        orcaslicer_settings={},
    )
    child = PrinterProfile(
        name="Voron 2.4 350 0.4 nozzle - Copy",
        slug="voron-child-projection",
        owner_user_id=auth_user.id,
        source="orcaslicer",
        is_official=False,
        active=True,
        orcaslicer_settings={"inherits": parent.name, "machine_max_acceleration_x": [9000]},
    )
    process = PrintProfile(
        name="0.20 mm Standard @Voron",
        slug="voron-process-projection",
        owner_user_id=auth_user.id,
        source="orcaslicer",
        active=True,
        configuration_links_resolved=True,
        orcaslicer_settings={"layer_height": "0.2"},
    )
    db_session.add_all([parent, child, process])
    await db_session.flush()

    await replace_configuration_links(
        db_session,
        profile=process,
        printer_profile_ids=[parent.id],
    )
    await db_session.commit()

    links = list(
        (
            await db_session.execute(
                select(PrintProfileConfigurationLink)
                .where(PrintProfileConfigurationLink.print_profile_id == process.id)
                .order_by(PrintProfileConfigurationLink.printer_profile_id)
            )
        ).scalars()
    )
    assert {(link.printer_profile_id, link.relation_type) for link in links} == {
        (parent.id, "explicit"),
        (child.id, "inherited_machine"),
    }


@pytest.mark.asyncio
async def test_factory_process_is_returned_for_user_machine_child(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    parent = PrinterProfile(
        name="Bambu Lab P2S 0.4 nozzle",
        slug="p2s-parent-runtime-projection",
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        orcaslicer_settings={},
    )
    child = PrinterProfile(
        name="Workshop P2S",
        slug="p2s-child-runtime-projection",
        owner_user_id=auth_user.id,
        source="orcaslicer",
        active=True,
        orcaslicer_settings={"inherits": parent.name},
    )
    process = PrintProfile(
        name="0.20 mm Standard @P2S",
        slug="p2s-process-runtime-projection",
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        configuration_links_resolved=True,
        orcaslicer_settings={"layer_height": "0.2"},
    )
    db_session.add_all([parent, child, process])
    await db_session.flush()
    db_session.add(
        PrintProfileConfigurationLink(
            print_profile_id=process.id,
            printer_profile_id=parent.id,
            relation_type="explicit",
        )
    )
    await db_session.commit()

    response = await auth_client.get(
        "/api/v1/print-profiles/",
        params={"printer_profile_ids": child.id, "size": 100},
    )

    assert response.status_code == 200
    item = next(item for item in response.json()["items"] if item["id"] == process.id)
    assert child.id in item["printer_profile_ids"]


@pytest.mark.asyncio
async def test_configuration_filter_returns_canonical_exact_and_model_processes(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    printer = Printer(
        name="Bambu Lab P2S",
        manufacturer="Bambu Lab",
        model="P2S",
        slug="bambu-lab-p2s-filter",
        source="system",
        active=True,
    )
    db_session.add(printer)
    await db_session.flush()
    configuration = PrinterProfile(
        name="Bambu Lab P2S 0.4 nozzle",
        slug="bambu-lab-p2s-04-filter",
        printer_id=printer.id,
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        orcaslicer_settings={"nozzle_diameter": ["0.4"]},
    )
    db_session.add(configuration)
    await db_session.flush()

    exact = PrintProfile(
        name="0.20 mm Standard P2S",
        slug="020-standard-p2s-filter",
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        configuration_links_resolved=True,
        orcaslicer_settings={"layer_height": "0.2"},
    )
    model = PrintProfile(
        name="0.28 mm Draft P2S",
        slug="028-draft-p2s-filter",
        owner_user_id=None,
        source="system",
        is_official=True,
        active=True,
        configuration_links_resolved=False,
        orcaslicer_settings={"layer_height": "0.28"},
    )
    model.printer_links = [
        PrintProfilePrinter(
            printer_id=printer.id,
            printer_slug=printer.slug,
            relation_type="explicit",
        )
    ]
    db_session.add_all([exact, model])
    await db_session.flush()
    db_session.add(
        PrintProfileConfigurationLink(
            print_profile_id=exact.id,
            printer_profile_id=configuration.id,
        )
    )
    await db_session.commit()

    response = await auth_client.get(
        "/api/v1/print-profiles/",
        params={"printer_profile_ids": configuration.id, "size": 100},
    )

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == {exact.id, model.id}


async def _configuration(
    db: AsyncSession,
    *,
    owner_user_id: int,
    name: str,
    slug: str,
) -> PrinterProfile:
    configuration = PrinterProfile(
        owner_user_id=owner_user_id,
        name=name,
        slug=slug,
        active=True,
        orcaslicer_settings={},
    )
    db.add(configuration)
    await db.commit()
    await db.refresh(configuration)
    return configuration


@pytest.mark.asyncio
async def test_owned_print_profile_links_exact_configurations_without_leaking(
    client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    first = await _configuration(
        db_session,
        owner_user_id=auth_user.id,
        name="Workshop machine 0.4",
        slug="workshop-machine-04",
    )
    second = await _configuration(
        db_session,
        owner_user_id=auth_user.id,
        name="Workshop machine 0.6",
        slug="workshop-machine-06",
    )
    foreign_user = User(
        email="foreign-process-owner@example.com",
        username="foreign-process-owner",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db_session.add(foreign_user)
    await db_session.commit()
    await db_session.refresh(foreign_user)
    foreign = await _configuration(
        db_session,
        owner_user_id=foreign_user.id,
        name="Foreign machine",
        slug="foreign-machine",
    )

    headers = {"Authorization": f"Bearer {create_access_token({'sub': auth_user.email})}"}
    created = await client.post(
        "/api/v1/print-profiles/",
        headers=headers,
        json={
            "name": "0.20 mm Workshop",
            "slug": "020-mm-workshop",
            "active": True,
            "printer_profile_ids": [first.id],
            "compatible_printers": [first.name],
            "orcaslicer_settings": {"layer_height": "0.2"},
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    assert created.json()["printer_profile_ids"] == [first.id]
    assert created.json()["configuration_links_resolved"] is True

    moved = await client.patch(
        f"/api/v1/print-profiles/{profile_id}",
        headers=headers,
        json={
            "printer_profile_ids": [second.id],
            "compatible_printers": [second.name],
        },
    )
    assert moved.status_code == 200
    assert moved.json()["printer_profile_ids"] == [second.id]

    rejected = await client.patch(
        f"/api/v1/print-profiles/{profile_id}",
        headers=headers,
        json={"printer_profile_ids": [foreign.id]},
    )
    assert rejected.status_code == 404

    anonymous_list = await client.get(
        "/api/v1/print-profiles/",
        params={"owner_user_id": auth_user.id, "active_only": "false"},
    )
    assert anonymous_list.status_code == 401
    anonymous_detail = await client.get(f"/api/v1/print-profiles/{profile_id}")
    assert anonymous_detail.status_code == 404
    anonymous_export = await client.get(
        f"/api/v1/print-profiles/{profile_id}/export/orcaslicer.json"
    )
    assert anonymous_export.status_code == 404

    private_configuration_list = await client.get(
        "/api/v1/printer-profiles/",
        params={"owner_user_id": auth_user.id, "active_only": "false"},
    )
    assert private_configuration_list.status_code == 401
    assert (await client.get(f"/api/v1/printer-profiles/{first.id}")).status_code == 404
    assert (
        await client.get(
            f"/api/v1/printer-profiles/{first.id}/export/orcaslicer.json"
        )
    ).status_code == 404

    official_configuration = PrinterProfile(
        name="Public official machine",
        slug="public-official-machine",
        is_official=True,
        active=True,
        orcaslicer_settings={"nozzle_diameter": ["0.4"]},
    )
    db_session.add(official_configuration)
    await db_session.commit()
    await db_session.refresh(official_configuration)

    public_configuration_list = await client.get("/api/v1/printer-profiles/")
    assert public_configuration_list.status_code == 200
    assert official_configuration.id in {
        item["id"] for item in public_configuration_list.json()["items"]
    }
    assert (
        await client.get(f"/api/v1/printer-profiles/{official_configuration.id}")
    ).status_code == 200
    assert (
        await client.get(
            f"/api/v1/printer-profiles/{official_configuration.id}/export/orcaslicer.json"
        )
    ).status_code == 200

    official = PrintProfile(
        name="Public official process",
        slug="public-official-process",
        is_official=True,
        active=True,
        orcaslicer_settings={"layer_height": "0.2"},
    )
    db_session.add(official)
    await db_session.commit()
    await db_session.refresh(official)

    public_list = await client.get("/api/v1/print-profiles/")
    assert public_list.status_code == 200
    assert official.id in {item["id"] for item in public_list.json()["items"]}
    assert (await client.get(f"/api/v1/print-profiles/{official.id}")).status_code == 200
    assert (
        await client.get(
            f"/api/v1/print-profiles/{official.id}/export/orcaslicer.json"
        )
    ).status_code == 200

    links = list(
        (
            await db_session.execute(
                select(PrintProfileConfigurationLink).where(
                    PrintProfileConfigurationLink.print_profile_id == profile_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert [link.printer_profile_id for link in links] == [second.id]


@pytest.mark.asyncio
async def test_orca_import_infers_an_unambiguous_owned_configuration(
    client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    configuration = await _configuration(
        db_session,
        owner_user_id=auth_user.id,
        name="Imported machine 0.4 nozzle",
        slug="imported-machine-04",
    )
    headers = {"Authorization": f"Bearer {create_access_token({'sub': auth_user.email})}"}

    imported = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "process-import-exact-config",
                    "name": "0.16 mm Optimal",
                    "compatible_printers": [configuration.name],
                    "orcaslicer_settings": {
                        "layer_height": "0.16",
                        "compatible_printers": [configuration.name],
                    },
                }
            ]
        },
    )
    assert imported.status_code == 200
    profile_id = imported.json()["results"][0]["fhub_id"]

    detail = await client.get(
        f"/api/v1/print-profiles/{profile_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["printer_profile_ids"] == [configuration.id]
    assert detail.json()["configuration_links_resolved"] is True

    official_configuration = PrinterProfile(
        name="Official imported machine",
        slug="official-imported-machine",
        owner_user_id=None,
        is_official=True,
        active=True,
        orcaslicer_settings={},
    )
    db_session.add(official_configuration)
    await db_session.commit()
    await db_session.refresh(official_configuration)

    partial = await client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        headers=headers,
        json={
            "profiles": [
                {
                    "external_id": "process-import-partial-config",
                    "name": "0.24 mm Partial",
                    "compatible_printers": [
                        configuration.name,
                        official_configuration.name,
                        "Configuration not imported yet",
                    ],
                    "orcaslicer_settings": {"layer_height": "0.24"},
                }
            ]
        },
    )
    assert partial.status_code == 200
    partial_detail = await client.get(
        f"/api/v1/print-profiles/{partial.json()['results'][0]['fhub_id']}",
        headers=headers,
    )
    assert partial_detail.status_code == 200
    assert partial_detail.json()["printer_profile_ids"] == sorted(
        [configuration.id, official_configuration.id]
    )
    assert partial_detail.json()["configuration_links_resolved"] is False
