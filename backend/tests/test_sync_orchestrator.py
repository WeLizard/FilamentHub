"""Tests for the SyncOrchestrator service.

Covers the actual public API of SyncOrchestrator:
- get_or_create_device — device registration/lookup
- create_sync_plan — full / incremental sync plan generation
- complete_sync — sync_version bump after a confirmed sync
- record_sync_success / record_sync_error — per-preset sync history
- get_deleted_presets — server-side deletion detection
- get_sync_status — last sync status for a device
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.preset import Preset, PresetModerationStatus
from app.models.filament import Filament
from app.models.brand import Brand
from app.models.sync_device import SyncDevice
from app.models.sync_history import SyncHistory, SyncStatus
from app.services.sync_orchestrator import SyncOrchestrator


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_brand(db_session: AsyncSession) -> Brand:
    """Create a test brand."""
    brand = Brand(
        name="Test Brand",
        slug="test-brand",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    return brand


@pytest_asyncio.fixture
async def test_filament(db_session: AsyncSession, test_brand: Brand) -> Filament:
    """Create a test filament."""
    filament = Filament(
        brand_id=test_brand.id,
        name="Test PLA",
        slug="test-pla",
        material_type="PLA",
        color_name="Red",
        color_hex="#FF0000",
        diameter=1.75,
        density=1.24,
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    return filament


@pytest_asyncio.fixture
async def test_preset(
    db_session: AsyncSession, test_user: User, test_filament: Filament
) -> Preset:
    """Create a test preset owned by test_user."""
    preset = Preset(
        name="Test Preset",
        description="Test preset description",
        filament_id=test_filament.id,
        user_id=test_user.id,
        extruder_temp=200.0,
        bed_temp=60.0,
        print_speed=100.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
        orcaslicer_settings={"temperature": 200, "bed_temperature": 60},
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)
    return preset


@pytest.fixture
def sync_orchestrator(db_session: AsyncSession) -> SyncOrchestrator:
    """Create a SyncOrchestrator instance bound to the test session."""
    return SyncOrchestrator(db_session)


@pytest.mark.asyncio
async def test_get_or_create_device_new(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """A new device is created with sync_version 0."""
    device_fingerprint = "test-device-001"
    orcaslicer_version = "1.9.0"

    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        orcaslicer_version=orcaslicer_version,
    )

    assert device is not None
    assert device.user_id == test_user.id
    assert device.device_fingerprint == device_fingerprint
    assert device.orcaslicer_version == orcaslicer_version
    assert device.sync_version == 0

    # Verify device was persisted
    result = await db_session.execute(
        select(SyncDevice).where(SyncDevice.device_fingerprint == device_fingerprint)
    )
    saved_device = result.scalar_one_or_none()
    assert saved_device is not None
    assert saved_device.id == device.id


@pytest.mark.asyncio
async def test_get_or_create_device_existing(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """An existing device is returned and its orcaslicer_version updated."""
    device_fingerprint = "test-device-002"

    existing_device = SyncDevice(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        orcaslicer_version="1.8.0",
        sync_version=5,
    )
    db_session.add(existing_device)
    await db_session.commit()
    await db_session.refresh(existing_device)

    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        orcaslicer_version="1.9.0",
    )

    assert device.id == existing_device.id
    # sync_version is preserved (get_or_create does not bump it)
    assert device.sync_version == 5
    # orcaslicer_version is refreshed
    assert device.orcaslicer_version == "1.9.0"


@pytest.mark.asyncio
async def test_create_sync_plan_full_sync(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Full sync returns all active presets of the user."""
    sync_plan = await sync_orchestrator.create_sync_plan(
        user_id=test_user.id,
        device_fingerprint="test-device-003",
        preset_type="filament",
        force_full_sync=True,
    )

    assert sync_plan is not None
    assert "to_download" in sync_plan
    assert "deleted_on_server" in sync_plan
    assert "conflicts" in sync_plan

    preset_ids = [p["id"] for p in sync_plan["to_download"]]
    assert test_preset.id in preset_ids


@pytest.mark.asyncio
async def test_create_sync_plan_incremental(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Incremental sync (sync_version > 0) returns a well-formed plan."""
    device_fingerprint = "test-device-004"

    device = SyncDevice(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        orcaslicer_version="1.9.0",
        sync_version=1,
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(device)
    await db_session.commit()

    sync_plan = await sync_orchestrator.create_sync_plan(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        preset_type="filament",
        force_full_sync=False,
    )

    assert sync_plan is not None
    assert "to_download" in sync_plan
    assert isinstance(sync_plan["to_download"], list)
    assert isinstance(sync_plan["conflicts"], list)


@pytest.mark.asyncio
async def test_complete_sync_increments_version(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """complete_sync bumps sync_version once and stamps last_sync_at."""
    device_fingerprint = "test-device-005"

    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
    )
    assert device.sync_version == 0

    updated = await sync_orchestrator.complete_sync(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
    )

    assert updated.sync_version == 1
    assert updated.last_sync_at is not None


@pytest.mark.asyncio
async def test_record_sync_success(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """record_sync_success writes a SUCCESS history row for a preset."""
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint="test-device-006",
    )

    history = await sync_orchestrator.record_sync_success(
        user_id=test_user.id,
        device_id=device.id,
        sync_version=device.sync_version,
        preset_type="filament",
        preset_id=test_preset.id,
        operation="download",
    )

    assert history is not None
    assert history.device_id == device.id
    assert history.preset_id == test_preset.id
    assert history.status == SyncStatus.SUCCESS

    result = await db_session.execute(
        select(SyncHistory).where(SyncHistory.device_id == device.id)
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.id == history.id


@pytest.mark.asyncio
async def test_record_sync_error(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """record_sync_error writes an ERROR history row with the message."""
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint="test-device-007",
    )

    error_message = "Network connection timeout"
    history = await sync_orchestrator.record_sync_error(
        user_id=test_user.id,
        device_id=device.id,
        sync_version=device.sync_version,
        preset_type="printer",
        preset_id=test_preset.id,
        error_message=error_message,
        operation="download",
    )

    assert history is not None
    assert history.status == SyncStatus.ERROR
    assert history.error_message == error_message


@pytest.mark.asyncio
async def test_get_deleted_presets(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """get_deleted_presets returns a list (empty for a brand-new device)."""
    deleted = await sync_orchestrator.get_deleted_presets(
        user_id=test_user.id,
        device_fingerprint="test-device-008",
        preset_type="filament",
    )

    assert isinstance(deleted, list)


@pytest.mark.asyncio
async def test_get_sync_status(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """get_sync_status returns device fingerprint, version and stats."""
    device_fingerprint = "test-device-009"

    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
    )

    await sync_orchestrator.record_sync_success(
        user_id=test_user.id,
        device_id=device.id,
        sync_version=device.sync_version,
        preset_type="filament",
        preset_id=1,
        operation="download",
    )

    status = await sync_orchestrator.get_sync_status(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
    )

    assert status is not None
    assert status["device_fingerprint"] == device_fingerprint
    assert status["sync_version"] == device.sync_version
    assert "last_sync_stats" in status
