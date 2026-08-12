"""Exact process-profile/configuration links and their account boundary."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.printer_profile import PrinterProfile
from app.models.user import User

from .conftest import accepted_legal


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
