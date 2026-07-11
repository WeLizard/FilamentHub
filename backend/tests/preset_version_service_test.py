"""Tests for preset version history service: dedup, squash, restore, diff."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_version import PresetVersionSource
from app.models.user import User
from app.services import preset_version_service as svc


async def _seed(db: AsyncSession) -> tuple[User, Preset]:
    user = User(
        email="pv-test@example.com",
        username="pv_test_user",
        password_hash="not-used",
        active=True,
    )
    db.add(user)
    await db.flush()

    preset = Preset(
        name="Test PLA",
        user_id=user.id,
        extruder_temp=210,
        bed_temp=60,
        orcaslicer_settings={"nozzle_temperature": "210", "filament_flow_ratio": "0.95"},
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(user)
    await db.refresh(preset)
    return user, preset


@pytest.mark.asyncio
async def test_first_version_is_v1(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    assert v is not None
    assert v.version_number == 1
    assert v.content_hash


@pytest.mark.asyncio
async def test_dedup_identical_settings_returns_none(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    # No change to orcaslicer_settings -> dedup.
    again = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    assert again is None


@pytest.mark.asyncio
async def test_changed_settings_create_new_version(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    preset.orcaslicer_settings = {"nozzle_temperature": "220", "filament_flow_ratio": "0.95"}
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    assert v2 is not None
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_structured_field_change_creates_new_version(db_session: AsyncSession):
    # A change to a structured field (extruder_temp) with the settings blob
    # unchanged must still be versioned — the hash covers the effective payload,
    # not just orcaslicer_settings. Previously this was deduped and lost.
    user, preset = await _seed(db_session)
    await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    preset.extruder_temp = 225  # structured only; orcaslicer_settings untouched
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    assert v2 is not None
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_orca_sync_squashes_within_window(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await db_session.commit()
    assert v1.version_number == 1
    assert v1.squash_count == 1

    # Second orca_sync change within window -> in-place squash, same row.
    preset.orcaslicer_settings = {"nozzle_temperature": "215"}
    v_squashed = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await db_session.commit()
    assert v_squashed.id == v1.id
    assert v_squashed.version_number == 1
    assert v_squashed.squash_count == 2
    assert v_squashed.snapshot_orcaslicer_settings == {"nozzle_temperature": "215"}


@pytest.mark.asyncio
async def test_orca_sync_outside_window_creates_new(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await db_session.commit()

    # Force v1 to be old (outside squash window).
    v1.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db_session.commit()

    preset.orcaslicer_settings = {"nozzle_temperature": "215"}
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await db_session.commit()
    assert v2.id != v1.id
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_labeled_version_not_squashed(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await svc.set_label(db_session, v1, "Stable", "good baseline")
    await db_session.commit()

    preset.orcaslicer_settings = {"nozzle_temperature": "215"}
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.ORCA_SYNC, user.id)
    await db_session.commit()
    # Labeled v1 is frozen -> new version, not squash.
    assert v2.id != v1.id
    assert v2.version_number == 2


@pytest.mark.asyncio
async def test_web_edit_never_squashes(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    preset.orcaslicer_settings = {"nozzle_temperature": "215"}
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    assert v2.version_number == 2  # explicit edits always separate


@pytest.mark.asyncio
async def test_restore_applies_snapshot_and_creates_version(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    # Edit to a different state (v2).
    preset.orcaslicer_settings = {"nozzle_temperature": "240"}
    preset.extruder_temp = 240
    await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    # Restore v1.
    new_v = await svc.restore_version(db_session, preset, v1, user.id)
    await db_session.commit()

    # Preset settings rolled back to v1's snapshot.
    assert preset.orcaslicer_settings == {"nozzle_temperature": "210", "filament_flow_ratio": "0.95"}
    assert preset.extruder_temp == 210
    # A new version recording the restore exists.
    assert new_v.version_number == 3
    assert new_v.change_source == PresetVersionSource.RESTORE
    assert new_v.restored_from_version_id == v1.id


@pytest.mark.asyncio
async def test_diff_is_human_readable(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    preset.orcaslicer_settings = {
        "nozzle_temperature": "220",      # mapped, changed
        "filament_flow_ratio": "0.95",    # unchanged
        "some_raw_key": "x",              # unmapped, added
    }
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()

    diff = svc.compute_diff(v1, v2)
    assert diff["from_version"] == 1
    assert diff["to_version"] == 2

    mapped = {c["key"]: c for c in diff["changes"]}
    assert "nozzle_temperature" in mapped
    assert mapped["nozzle_temperature"]["label"] == "Nozzle temperature"
    assert mapped["nozzle_temperature"]["unit"] == "°C"
    assert mapped["nozzle_temperature"]["old"] == "210"
    assert mapped["nozzle_temperature"]["new"] == "220"
    # unchanged field absent
    assert "filament_flow_ratio" not in mapped

    unmapped = {c["key"] for c in diff["unmapped_changes"]}
    assert "some_raw_key" in unmapped


@pytest.mark.asyncio
async def test_list_labeled_only_filter(db_session: AsyncSession):
    user, preset = await _seed(db_session)
    v1 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await db_session.commit()
    preset.orcaslicer_settings = {"nozzle_temperature": "220"}
    v2 = await svc.record_version(db_session, preset, PresetVersionSource.WEB_EDIT, user.id)
    await svc.set_label(db_session, v2, "Tuned", None)
    await db_session.commit()

    all_versions, total_all = await svc.list_versions(db_session, preset.id, labeled_only=False)
    assert total_all == 2

    labeled, total_labeled = await svc.list_versions(db_session, preset.id, labeled_only=True)
    assert total_labeled == 1
    assert labeled[0].id == v2.id
