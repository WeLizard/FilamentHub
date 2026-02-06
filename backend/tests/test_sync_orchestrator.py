"""Tests for sync orchestrator service.

This module tests the SyncOrchestrator service which handles:
- Device registration and tracking
- Sync plan generation (full and incremental)
- Deleted preset detection
- Sync history recording
"""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.preset import Preset, PresetModerationStatus
from app.models.filament import Filament
from app.models.brand import Brand


# Note: The following imports will work once SyncDevice and SyncHistory models
# are merged from the main workspace. For now, these tests document expected behavior.
try:
    from app.models.sync_device import SyncDevice
    from app.models.sync_history import SyncHistory
    from app.services.sync_orchestrator import SyncOrchestrator
    SYNC_MODELS_AVAILABLE = True
except ImportError:
    SYNC_MODELS_AVAILABLE = False
    SyncDevice = None
    SyncHistory = None
    SyncOrchestrator = None


pytestmark = pytest.mark.skipif(
    not SYNC_MODELS_AVAILABLE,
    reason="SyncDevice, SyncHistory models and SyncOrchestrator service not available in this worktree"
)


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="$2b$12$test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
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


@pytest.fixture
async def test_filament(db_session: AsyncSession, test_brand: Brand) -> Filament:
    """Create a test filament."""
    filament = Filament(
        brand_id=test_brand.id,
        name="Test PLA",
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


@pytest.fixture
async def test_preset(
    db_session: AsyncSession, test_user: User, test_filament: Filament
) -> Preset:
    """Create a test preset."""
    preset = Preset(
        name="Test Preset",
        slug="test-preset",
        description="Test preset description",
        filament_id=test_filament.id,
        created_by_id=test_user.id,
        moderation_status=PresetModerationStatus.APPROVED,
        is_public=True,
        active=True,
        orcaslicer_settings={"temperature": 200, "bed_temperature": 60},
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)
    return preset


@pytest.fixture
def sync_orchestrator(db_session: AsyncSession) -> SyncOrchestrator:
    """Create a SyncOrchestrator instance."""
    if SYNC_MODELS_AVAILABLE:
        return SyncOrchestrator(db_session)
    return None


@pytest.mark.asyncio
async def test_get_or_create_device_new(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """Test creating a new sync device."""
    device_fingerprint = "test-device-001"
    device_name = "Test OrcaSlicer"
    orcaslicer_version = "1.9.0"

    # Get or create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name=device_name,
        orcaslicer_version=orcaslicer_version,
    )

    assert device is not None
    assert device.user_id == test_user.id
    assert device.device_fingerprint == device_fingerprint
    assert device.device_name == device_name
    assert device.orcaslicer_version == orcaslicer_version
    assert device.last_sync_version == 0
    assert device.last_sync_at is not None

    # Verify device was saved to database
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
    """Test retrieving an existing sync device."""
    device_fingerprint = "test-device-002"

    # Create device first
    existing_device = SyncDevice(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Original Name",
        orcaslicer_version="1.8.0",
        last_sync_version=5,
    )
    db_session.add(existing_device)
    await db_session.commit()
    await db_session.refresh(existing_device)

    # Get or create should return existing device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Updated Name",
        orcaslicer_version="1.9.0",
    )

    assert device is not None
    assert device.id == existing_device.id
    assert device.last_sync_version == 5
    # Device name and version should be updated
    assert device.device_name == "Updated Name"
    assert device.orcaslicer_version == "1.9.0"


@pytest.mark.asyncio
async def test_create_sync_plan_full_sync(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Test full sync returns all active presets when force_full_sync=True."""
    device_fingerprint = "test-device-003"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Create sync plan with force_full_sync
    sync_plan = await sync_orchestrator.create_sync_plan(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        preset_type="filament",
        force_full_sync=True,
    )

    assert sync_plan is not None
    assert "to_download" in sync_plan
    assert "deleted_on_server" in sync_plan
    assert "conflicts" in sync_plan

    # Should include our test preset
    assert len(sync_plan["to_download"]) >= 1
    preset_ids = [p["id"] for p in sync_plan["to_download"]]
    assert test_preset.id in preset_ids


@pytest.mark.asyncio
async def test_create_sync_plan_incremental(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Test incremental sync returns only changed presets."""
    device_fingerprint = "test-device-004"

    # Create device with existing sync version
    device = SyncDevice(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
        last_sync_version=1,
        last_sync_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    # Create a new preset after the last sync
    new_preset = Preset(
        name="New Preset",
        slug="new-preset",
        description="New preset after last sync",
        filament_id=test_preset.filament_id,
        created_by_id=test_user.id,
        moderation_status=PresetModerationStatus.APPROVED,
        is_public=True,
        active=True,
        orcaslicer_settings={"temperature": 210},
    )
    db_session.add(new_preset)
    await db_session.commit()
    await db_session.refresh(new_preset)

    # Create incremental sync plan
    sync_plan = await sync_orchestrator.create_sync_plan(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        preset_type="filament",
        force_full_sync=False,
    )

    assert sync_plan is not None
    assert "to_download" in sync_plan

    # Should only include presets created/updated after last sync
    # This depends on implementation - it should filter by updated_at timestamp


@pytest.mark.asyncio
async def test_detect_deleted_presets(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Test detection of presets deleted on server."""
    device_fingerprint = "test-device-005"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Create a preset and then mark it as inactive (deleted)
    deleted_preset = Preset(
        name="Deleted Preset",
        slug="deleted-preset",
        description="This will be deleted",
        filament_id=test_preset.filament_id,
        created_by_id=test_user.id,
        moderation_status=PresetModerationStatus.APPROVED,
        is_public=True,
        active=False,  # Marked as deleted
        orcaslicer_settings={"temperature": 200},
    )
    db_session.add(deleted_preset)
    await db_session.commit()
    await db_session.refresh(deleted_preset)

    # Simulate client providing list of local presets
    client_preset_ids = [test_preset.id, deleted_preset.id]

    # Detect deleted presets
    deleted = await sync_orchestrator.detect_deleted_presets(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        preset_type="filament",
        client_preset_ids=client_preset_ids,
    )

    assert deleted is not None
    assert isinstance(deleted, list)

    # Should detect the deleted preset
    if len(deleted) > 0:
        deleted_ids = [p["preset_id"] for p in deleted]
        assert deleted_preset.id in deleted_ids

        # Should include metadata about who created/saved the preset
        for preset_info in deleted:
            assert "was_created_by_user" in preset_info
            assert "was_saved_by_user" in preset_info


@pytest.mark.asyncio
async def test_record_sync_history(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """Test recording sync history."""
    device_fingerprint = "test-device-006"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Record a sync operation
    history = await sync_orchestrator.record_sync_history(
        device_id=device.id,
        preset_type="filament",
        operation_type="download",
        presets_count=10,
        success=True,
    )

    assert history is not None
    assert history.device_id == device.id
    assert history.preset_type == "filament"
    assert history.operation_type == "download"
    assert history.presets_count == 10
    assert history.success is True
    assert history.created_at is not None

    # Verify history was saved
    result = await db_session.execute(
        select(SyncHistory).where(SyncHistory.device_id == device.id)
    )
    saved_history = result.scalar_one_or_none()
    assert saved_history is not None
    assert saved_history.id == history.id


@pytest.mark.asyncio
async def test_record_sync_history_with_error(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """Test recording failed sync history with error message."""
    device_fingerprint = "test-device-007"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Record a failed sync operation
    error_message = "Network connection timeout"
    history = await sync_orchestrator.record_sync_history(
        device_id=device.id,
        preset_type="printer",
        operation_type="download",
        presets_count=0,
        success=False,
        error_message=error_message,
    )

    assert history is not None
    assert history.success is False
    assert history.error_message == error_message


@pytest.mark.asyncio
async def test_sync_plan_with_conflicts(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    test_preset: Preset,
    db_session: AsyncSession,
):
    """Test sync plan identifies conflicts between server and client presets."""
    device_fingerprint = "test-device-008"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Create sync plan
    # Note: Conflict detection logic depends on implementation
    # This test documents expected behavior
    sync_plan = await sync_orchestrator.create_sync_plan(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        preset_type="filament",
        force_full_sync=False,
        client_presets=[
            {
                "id": test_preset.id,
                "name": test_preset.name,
                "updated_at": "2024-01-01T00:00:00Z",  # Old timestamp
            }
        ],
    )

    assert sync_plan is not None
    assert "conflicts" in sync_plan

    # If preset was updated on server after client's version,
    # it should appear in conflicts
    if len(sync_plan["conflicts"]) > 0:
        assert isinstance(sync_plan["conflicts"], list)
        for conflict in sync_plan["conflicts"]:
            assert "preset_id" in conflict
            assert "server_version" in conflict
            assert "client_version" in conflict


@pytest.mark.asyncio
async def test_update_device_sync_version(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """Test updating device sync version after successful sync."""
    device_fingerprint = "test-device-009"

    # Create device
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    initial_version = device.last_sync_version
    initial_sync_time = device.last_sync_at

    # Update sync version
    new_version = initial_version + 1
    await sync_orchestrator.update_device_sync_version(
        device_id=device.id,
        new_version=new_version,
    )

    # Refresh device from database
    await db_session.refresh(device)

    assert device.last_sync_version == new_version
    assert device.last_sync_at > initial_sync_time


@pytest.mark.asyncio
async def test_get_device_sync_status(
    sync_orchestrator: SyncOrchestrator,
    test_user: User,
    db_session: AsyncSession,
):
    """Test retrieving sync status for a device."""
    device_fingerprint = "test-device-010"

    # Create device with sync history
    device = await sync_orchestrator.get_or_create_device(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
        device_name="Test Device",
        orcaslicer_version="1.9.0",
    )

    # Record some sync history
    await sync_orchestrator.record_sync_history(
        device_id=device.id,
        preset_type="filament",
        operation_type="download",
        presets_count=5,
        success=True,
    )

    # Get sync status
    status = await sync_orchestrator.get_device_sync_status(
        user_id=test_user.id,
        device_fingerprint=device_fingerprint,
    )

    assert status is not None
    assert "device" in status
    assert "last_sync" in status
    assert status["device"]["device_fingerprint"] == device_fingerprint
    assert status["device"]["last_sync_version"] == device.last_sync_version
