"""Per-user preset version selection and update acknowledgement."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_version import PresetVersionSource
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.services import preset_version_service
from app.services.preset_publication import apply_managed_orca_identity
from tests.conftest import registration_payload


async def _signed_in(client: AsyncClient, suffix: str) -> dict[str, str]:
    email = f"version-selection-{suffix}@example.com"
    password = "testpassword123"
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email,
            username=f"version_selection_{suffix}",
            password=password,
        ),
    )
    assert registered.status_code == 201
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


async def _published_preset(db: AsyncSession, suffix: str) -> Preset:
    brand = Brand(
        name=f"Version Brand {suffix}",
        slug=f"version-brand-{suffix}",
        active=True,
    )
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name=f"Version PETG {suffix}",
        slug=f"version-petg-{suffix}",
        material_type="PETG",
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.flush()
    preset = Preset(
        filament_id=filament.id,
        name=f"Version preset {suffix}",
        is_official=True,
        extruder_temp=230,
        bed_temp=75,
        orcaslicer_settings={"nozzle_temperature": ["230"]},
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db.add(preset)
    await db.flush()
    apply_managed_orca_identity(preset)
    await db.flush()
    return preset


@pytest.mark.asyncio
async def test_saved_user_keeps_selected_version_until_accepting_update(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _signed_in(client, "manual")
    preset = await _published_preset(db_session, "manual")
    v1 = await preset_version_service.record_version(
        db_session, preset, PresetVersionSource.WEB_EDIT
    )
    await db_session.commit()

    saved = await client.post(
        "/api/v1/saved-presets/",
        headers=headers,
        json={"preset_id": preset.id},
    )
    assert saved.status_code == 201
    assert saved.json()["selected_version_id"] == v1.id

    preset.extruder_temp = 240
    preset.orcaslicer_settings = {
        **preset.orcaslicer_settings,
        "nozzle_temperature": ["240"],
    }
    v2 = await preset_version_service.record_version(
        db_session, preset, PresetVersionSource.WEB_EDIT
    )
    await db_session.commit()

    listed = await client.get("/api/v1/saved-presets/", headers=headers)
    state = listed.json()["items"][0]
    assert state["selected_version_id"] == v1.id
    assert state["latest_version_id"] == v2.id
    assert state["update_available"] is True
    assert state["update_unseen"] is True

    kept = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/version",
        headers=headers,
        json={"action": "keep_current", "version_id": v2.id},
    )
    assert kept.status_code == 200
    assert kept.json()["selected_version_id"] == v1.id
    assert kept.json()["update_available"] is True
    assert kept.json()["update_unseen"] is False

    accepted = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/version",
        headers=headers,
        json={"action": "select", "version_id": v2.id},
    )
    assert accepted.status_code == 200
    assert accepted.json()["selected_version_id"] == v2.id
    assert accepted.json()["update_available"] is False

    preset.extruder_temp = 245
    preset.orcaslicer_settings = {
        **preset.orcaslicer_settings,
        "nozzle_temperature": ["245"],
    }
    v3 = await preset_version_service.record_version(
        db_session, preset, PresetVersionSource.WEB_EDIT
    )
    await db_session.commit()

    listed_again = await client.get("/api/v1/saved-presets/", headers=headers)
    next_state = listed_again.json()["items"][0]
    assert next_state["selected_version_id"] == v2.id
    assert next_state["latest_version_id"] == v3.id

    stale_keep = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/version",
        headers=headers,
        json={"action": "keep_current", "version_id": v2.id},
    )
    assert stale_keep.status_code == 404

    desired = await client.get("/api/v1/auth/my-presets", headers=headers)
    assert desired.status_code == 200
    desired_item = desired.json()["items"][0]
    assert desired_item["id"] == preset.id
    assert desired_item["selected_version_id"] == v2.id
    assert desired_item["selected_version_number"] == 2
    assert desired_item["latest_version_id"] == v3.id
    assert desired_item["latest_version_number"] == 3
    assert desired_item["update_available"] is True


@pytest.mark.asyncio
async def test_saving_legacy_public_preset_creates_and_pins_initial_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _signed_in(client, "legacy")
    await _signed_in(client, "legacy-null")
    legacy_user = await db_session.scalar(
        select(User).where(
            User.email == "version-selection-legacy-null@example.com"
        )
    )
    assert legacy_user is not None
    preset = await _published_preset(db_session, "legacy")
    legacy_saved = UserSavedPreset(
        user_id=legacy_user.id,
        preset_id=preset.id,
        sync=True,
    )
    db_session.add(legacy_saved)
    await db_session.commit()

    saved = await client.post(
        "/api/v1/saved-presets/",
        headers=headers,
        json={"preset_id": preset.id},
    )

    assert saved.status_code == 201
    version_id = saved.json()["selected_version_id"]
    assert version_id is not None
    assert saved.json()["latest_version_id"] == version_id
    version = await preset_version_service.get_version(
        db_session,
        preset.id,
        version_id,
    )
    assert version is not None
    assert version.change_source == PresetVersionSource.MIGRATION
    assert version.snapshot_orcaslicer_settings["fhub_source"] == "filamenthub"
    assert str(version.snapshot_orcaslicer_settings["fhub_id"]) == str(preset.id)
    await db_session.refresh(legacy_saved)
    assert legacy_saved.selected_version_id == version_id
    assert legacy_saved.seen_version_id == version_id


@pytest.mark.asyncio
async def test_orca_export_uses_the_users_selected_immutable_version(
    client: AsyncClient,
    db_session: AsyncSession,
):
    headers = await _signed_in(client, "export")
    preset = await _published_preset(db_session, "export")
    v1 = await preset_version_service.record_version(
        db_session, preset, PresetVersionSource.WEB_EDIT
    )
    preset.extruder_temp = 250
    preset.orcaslicer_settings = {
        **preset.orcaslicer_settings,
        "nozzle_temperature": ["250"],
    }
    await preset_version_service.record_version(
        db_session, preset, PresetVersionSource.WEB_EDIT
    )
    await db_session.commit()

    exported = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json",
        params={"version_id": v1.id},
        headers=headers,
    )
    assert exported.status_code == 200
    assert exported.json()["nozzle_temperature"] == ["230"]


@pytest.mark.asyncio
async def test_orca_squash_cannot_mutate_a_version_selected_by_another_user(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _signed_in(client, "owner")
    await _signed_in(client, "follower")
    owner = await db_session.scalar(
        select(User).where(User.email == "version-selection-owner@example.com")
    )
    follower = await db_session.scalar(
        select(User).where(User.email == "version-selection-follower@example.com")
    )
    assert owner is not None
    assert follower is not None

    preset = await _published_preset(db_session, "pinned-squash")
    preset.is_official = False
    preset.user_id = owner.id
    v1 = await preset_version_service.record_version(
        db_session,
        preset,
        PresetVersionSource.ORCA_SYNC,
        user_id=owner.id,
    )
    assert v1 is not None
    db_session.add(
        UserSavedPreset(
            user_id=follower.id,
            preset_id=preset.id,
            sync=True,
            selected_version_id=v1.id,
            seen_version_id=v1.id,
        )
    )
    await db_session.flush()

    preset.extruder_temp = 255
    preset.orcaslicer_settings = {
        **preset.orcaslicer_settings,
        "nozzle_temperature": ["255"],
    }
    v2 = await preset_version_service.record_version(
        db_session,
        preset,
        PresetVersionSource.ORCA_SYNC,
        user_id=owner.id,
        parent_version_id=v1.id,
    )

    assert v2 is not None
    assert v2.id != v1.id
    assert v2.version_number == 2
    assert v2.parent_version_id == v1.id
    assert v1.snapshot_orcaslicer_settings["nozzle_temperature"] == ["230"]
