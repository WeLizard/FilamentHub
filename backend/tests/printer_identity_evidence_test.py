"""Costly regressions: phantom printers, mistaken identity and destructive repair."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.core.field_encryption import encrypt_field
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.print_job import PrintJob, PrintJobStatus
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_identity import PrinterIdentity
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn
from app.services.orca_slice_report_service import _resolve_printer
from app.services.physical_printer_discovery_service import (
    current_printer_context,
    list_pending_connections,
    reconcile_user_printers,
)
from app.services.printer_connection_observation_service import record_observations
from app.services.printer_identity_service import discovery_key, endpoint_token


async def observe(db, user, source, items):
    await record_observations(
        db, user.id, source, [PrinterConnectionObservationIn(**i) for i in items], commit=False
    )
    return await reconcile_user_printers(db, user.id, source_instance_id=source)


@pytest.mark.parametrize("provider", ["moonraker", "octoprint", "bambu", "prusalink"])
async def test_three_identical_printers_shared_configuration_and_repeated_sync(
    db_session, auth_user, provider
):
    profile = PrinterProfile(
        owner_user_id=auth_user.id, name="Shared configuration", slug="shared", setting_id="shared"
    )
    db_session.add(profile)
    await db_session.commit()
    items = [
        dict(
            connection_ref=f"device-{i}",
            endpoint_token=str(i) * 64,
            has_connection=True,
            host_type=provider,
            preset_name=profile.name,
            printer_settings_id="shared",
            printer_model="Identical model",
        )
        for i in range(3)
    ]
    items.append(
        dict(preset_name="Stock nozzle 0.6", is_system=True, is_visible=True, is_current=True)
    )
    assert await observe(db_session, auth_user, "desktop", items) == 3
    original = set((await db_session.execute(select(UserPrinterDevice.id))).scalars())
    items.append(dict(items[0], connection_ref="second-preset-same-device"))
    assert await observe(db_session, auth_user, "desktop", items) == 0
    assert await observe(db_session, auth_user, "desktop", items) == 0
    assert set((await db_session.execute(select(UserPrinterDevice.id))).scalars()) == original
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterProfileLink)) == 3
    assert (
        len(
            set(
                (
                    await db_session.execute(select(PrinterConnectionBinding.physical_printer_id))
                ).scalars()
            )
        )
        == 3
    )


async def test_device_identity_survives_source_change_but_replacement_blocks_all_consumers(
    db_session, auth_user
):
    profile = PrinterProfile(
        owner_user_id=auth_user.id, name="Voron", slug="voron", setting_id="voron"
    )
    db_session.add(profile)
    await db_session.commit()
    item = dict(
        connection_ref="old-ref",
        endpoint_token="a" * 64,
        host_type="moonraker",
        preset_name="Voron",
        printer_settings_id="voron",
        is_current=True,
        device_identity={"kind": "moonraker_instance", "token": "c" * 64},
    )
    assert await observe(db_session, auth_user, "old-installation", [item]) == 1
    item.update(connection_ref="new-ref", endpoint_token="b" * 64)
    assert await observe(db_session, auth_user, "new-installation", [item]) == 0
    item.update(
        connection_ref="another-ref",
        device_identity={"kind": "moonraker_instance", "token": "d" * 64},
    )
    assert await observe(db_session, auth_user, "new-installation", [item]) == 0
    assert len(await list_pending_connections(db_session, auth_user.id)) == 1
    assert await db_session.scalar(select(func.count()).select_from(PrinterIdentity)) == 1
    assert (await current_printer_context(db_session, auth_user.id))["physical_printer_id"] is None
    assert await _resolve_printer(
        db_session,
        user_id=auth_user.id,
        printer_settings_id="Voron",
        fhub_printer_profile_id=profile.id,
        source_instance_id="new-installation",
    ) == (None, profile.id)


async def test_pending_new_device_resolution_is_replay_safe(auth_client, db_session, auth_user):
    item = dict(
        connection_ref="device-a",
        endpoint_token="a" * 64,
        host_type="octoprint",
        preset_name="Printer",
    )
    await observe(db_session, auth_user, "first-network", [item])
    await observe(db_session, auth_user, "another-network", [dict(item, connection_ref="device-b")])
    pending = await list_pending_connections(db_session, auth_user.id)
    assert len(pending) == 1
    path = f'/api/v1/orcaslicer/printer-connections/pending/{pending[0]["id"]}/resolve'
    for _ in range(2):
        response = await auth_client.post(
            path, json={"create_new": True, "revision": pending[0]["revision"]}
        )
        assert response.status_code == 204, response.text
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 2
    assert not await list_pending_connections(db_session, auth_user.id)
    # A further preset of that explicitly separate device reuses the saved choice.
    assert (
        await observe(
            db_session, auth_user, "another-network", [dict(item, connection_ref="device-c")]
        )
        == 0
    )
    assert not await list_pending_connections(db_session, auth_user.id)


async def test_merge_repairs_old_wrong_binding_preserving_feed_spool_and_history(
    auth_client, db_session, auth_user
):
    key = await discovery_key(db_session, auth_user.id)
    target = UserPrinterDevice(
        user_id=auth_user.id, name="Workshop Voron", supports_hh=True, api_key="keep-key"
    )
    duplicate = UserPrinterDevice(user_id=auth_user.id, name="Voron duplicate")
    profile = PrinterProfile(
        owner_user_id=auth_user.id, name="Voron", slug="voron", setting_id="voron"
    )
    db_session.add_all([target, duplicate, profile])
    await db_session.flush()
    target_id, duplicate_id = target.id, duplicate.id
    system = MaterialSystem(
        user_id=auth_user.id, physical_printer_id=target.id, name="HH", provider="happy_hare"
    )
    spool = UserSpool(
        user_id=auth_user.id, initial_weight_g=1000, used_weight_g=123, state=UserSpoolState.active
    )
    job = PrintJob(
        user_id=auth_user.id,
        physical_printer_id=duplicate.id,
        title="Earlier print",
        status=PrintJobStatus.completed,
        source="manual",
        source_ref="old",
        source_payload_hash="a" * 64,
        printer_name_snapshot="Voron duplicate",
    )
    bindings = [
        PrinterConnectionBinding(
            user_id=auth_user.id,
            physical_printer_id=target.id,
            normalized_endpoint="legacy",
            endpoint_ciphertext=encrypt_field("192.168.0.122:7125"),
            provider="moonraker",
        ),
        PrinterConnectionBinding(
            user_id=auth_user.id,
            physical_printer_id=duplicate.id,
            normalized_endpoint="new",
            source_instance_id="current-orca",
            connection_ref="new-ref",
            provider="moonraker",
        ),
    ]
    db_session.add_all(
        [
            system,
            spool,
            job,
            *bindings,
            UserPrinterProfileLink(
                user_id=auth_user.id,
                physical_printer_id=duplicate.id,
                printer_profile_id=profile.id,
            ),
        ]
    )
    await db_session.flush()
    slot = MaterialSlot(user_id=auth_user.id, material_system_id=system.id, provider_index=0)
    db_session.add(slot)
    await db_session.flush()
    assignment = MaterialSlotAssignment(
        user_id=auth_user.id,
        material_slot_id=slot.id,
        spool_id=spool.id,
        source="web",
        source_ts=datetime.now(timezone.utc),
        active=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    before = (system.id, slot.id, assignment.id, spool.id)
    item = dict(
        connection_ref="new-ref",
        endpoint_token=endpoint_token(key, "192.168.0.122:7125", "moonraker"),
        preset_name="Voron",
        printer_settings_id="voron",
        host_type="moonraker",
        is_current=True,
    )
    assert await observe(db_session, auth_user, "current-orca", [item]) == 0
    assert len(await list_pending_connections(db_session, auth_user.id)) == 1
    response = await auth_client.get(
        f"/api/v1/physical-printers/{duplicate_id}/merge-preview", params={"target_id": target_id}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["allowed"] and preview["history"] == 1
    response = await auth_client.post(
        f"/api/v1/physical-printers/{duplicate_id}/merge",
        json={"target_id": target_id, "revision": preview["revision"]},
    )
    assert response.status_code == 204, response.text
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1
    for entity in (target, system, slot, assignment, spool, job):
        await db_session.refresh(entity)
    assert before == (system.id, slot.id, assignment.id, spool.id)
    assert spool.used_weight_g == 123 and assignment.spool_id == spool.id
    assert target.name == "Workshop Voron" and target.api_key == "keep-key"
    assert job.physical_printer_id == target.id and job.printer_name_snapshot == "Voron duplicate"
    assert await observe(db_session, auth_user, "current-orca", [item]) == 0
    assert not await list_pending_connections(db_session, auth_user.id)
    assert {
        b.physical_printer_id
        for b in (await db_session.execute(select(PrinterConnectionBinding))).scalars()
    } == {target_id}


async def test_account_discovery_key_survives_encryption_rotation(
    db_session, auth_user, monkeypatch
):
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "old-encryption-key")
    key = await discovery_key(db_session, auth_user.id)
    await db_session.commit()
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_KEY", "rotated-encryption-key")
    monkeypatch.setattr(settings, "FIELD_ENCRYPTION_PREVIOUS_KEYS", ["old-encryption-key"])
    assert await discovery_key(db_session, auth_user.id) == key


async def test_partial_and_empty_snapshots_do_not_create_or_forget_devices(auth_client, db_session):
    path = "/api/v1/orcaslicer/printer-connections/observe"
    payload = {
        "source_instance_id": "desktop",
        "observations": [
            {
                "connection_ref": "local-device",
                "endpoint_token": "a" * 64,
                "host_type": "octoprint",
            },
        ],
    }
    assert (await auth_client.post(path, json=payload)).json()["created"] == 1
    for complete, status in [(False, "bound"), (True, "disconnected")]:
        response = await auth_client.post(
            path, json={**payload, "observations": [], "snapshot_complete": complete}
        )
        assert response.status_code == 200, response.text
        binding = await db_session.scalar(
            select(PrinterConnectionBinding).execution_options(populate_existing=True)
        )
        assert binding.status == status
        assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1
    assert (await auth_client.post(path, json=payload)).json()["created"] == 0
    binding = await db_session.scalar(
        select(PrinterConnectionBinding).execution_options(populate_existing=True)
    )
    assert binding.status == "bound"


async def test_merge_does_not_reactivate_a_removed_connection(auth_client, db_session, auth_user):
    source = UserPrinterDevice(user_id=auth_user.id, name="Duplicate")
    target = UserPrinterDevice(user_id=auth_user.id, name="Main")
    db_session.add_all([source, target])
    await db_session.flush()
    binding = PrinterConnectionBinding(
        user_id=auth_user.id,
        physical_printer_id=target.id,
        normalized_endpoint="removed",
        source_instance_id="desktop",
        connection_ref="removed-preset",
        status="disconnected",
    )
    db_session.add(binding)
    await db_session.commit()
    path = f"/api/v1/physical-printers/{source.id}"
    preview = (
        await auth_client.get(path + "/merge-preview", params={"target_id": target.id})
    ).json()
    response = await auth_client.post(
        path + "/merge", json={"target_id": target.id, "revision": preview["revision"]}
    )
    assert response.status_code == 204, response.text
    await db_session.refresh(binding)
    assert binding.status == "disconnected"


async def test_connection_confirmation_rejects_evidence_changed_after_preview(
    auth_client, db_session, auth_user
):
    item = dict(
        connection_ref="local",
        endpoint_token="a" * 64,
        host_type="moonraker",
        preset_name="Printer",
    )
    await observe(db_session, auth_user, "first", [item])
    await observe(db_session, auth_user, "second", [item])
    pending = (await list_pending_connections(db_session, auth_user.id))[0]
    # Same row/ref/address, but the device changed while the dialog was open.
    await observe(
        db_session,
        auth_user,
        "second",
        [
            {
                **item,
                "device_identity": {
                    "kind": "moonraker_instance",
                    "token": "b" * 64,
                },
            }
        ],
    )
    response = await auth_client.post(
        f'/api/v1/orcaslicer/printer-connections/pending/{pending["id"]}/resolve',
        json={"create_new": True, "revision": pending["revision"]},
    )
    assert response.status_code == 409, response.text
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 1


async def test_merge_rejects_foreign_target_stale_preview_and_feed_source(
    auth_client, db_session, auth_user, admin_user
):
    source = UserPrinterDevice(user_id=auth_user.id, name="Duplicate")
    target = UserPrinterDevice(user_id=auth_user.id, name="Main")
    foreign = UserPrinterDevice(user_id=admin_user.id, name="Not owned")
    db_session.add_all([source, target, foreign])
    await db_session.commit()
    path = f"/api/v1/physical-printers/{source.id}"
    assert (
        await auth_client.get(path + "/merge-preview", params={"target_id": foreign.id})
    ).status_code == 404
    assert (
        await auth_client.get(path + "/merge-preview", params={"target_id": source.id})
    ).status_code == 409
    preview = (
        await auth_client.get(path + "/merge-preview", params={"target_id": target.id})
    ).json()
    # A newly added connection invalidates the exact evidence the user reviewed.
    db_session.add(
        PrinterConnectionBinding(
            user_id=auth_user.id,
            physical_printer_id=source.id,
            normalized_endpoint="added-after-preview",
        )
    )
    await db_session.commit()
    response = await auth_client.post(
        path + "/merge", json={"target_id": target.id, "revision": preview["revision"]}
    )
    assert response.status_code == 409
    source.supports_hh = True
    await db_session.commit()
    preview = (
        await auth_client.get(path + "/merge-preview", params={"target_id": target.id})
    ).json()
    assert preview["allowed"] is False and preview["reason"] == "source_connected"
    assert await db_session.scalar(select(func.count()).select_from(UserPrinterDevice)) == 3
