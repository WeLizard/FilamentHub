"""Tests for presets endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.services.organization_access import grant_brand_owner_membership


async def _register_and_login(
    client: AsyncClient,
    suffix: str,
) -> tuple[dict[str, str], str]:
    """Register a user and return auth headers + email."""
    email = f"{suffix}@example.com"
    password = "testpassword123"

    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": f"user_{suffix}",
            "password": password,
            "role": "user",
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


@pytest.mark.asyncio
async def test_list_presets_empty(client: AsyncClient):
    """Test listing presets when database is empty."""
    response = await client.get("/api/v1/presets/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_create_preset(client: AsyncClient, db_session: AsyncSession):
    """Test creating a preset."""
    headers, _ = await _register_and_login(client, "preset-create")

    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Create preset
    preset_data = {
        "filament_id": filament.id,
        "name": "Test Preset",
        "description": "Test preset description",
        "is_official": False,
        "extruder_temp": 200.0,
        "bed_temp": 60.0,
        "print_speed": 50.0,
        "travel_speed": 150.0,
        "layer_height": 0.2,
        "flow_rate": 100.0,
        "fan_speed": 100,
        "retraction_length": 5.0,
        "retraction_speed": 45.0,
    }
    response = await client.post("/api/v1/presets/", json=preset_data, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == preset_data["name"]
    assert data["filament_id"] == filament.id
    assert data["id"] is not None
    # User presets are auto-approved on create (unless hard validation fails)
    assert data["moderation_status"] == "approved"


@pytest.mark.asyncio
async def test_create_official_preset(client: AsyncClient, db_session: AsyncSession):
    """Test creating an official preset (should be auto-approved)."""
    headers, email = await _register_and_login(client, "preset-official")

    # Create verified brand and filament (official presets require a verified brand)
    brand = Brand(name="Test Brand", slug="test-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-official",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    # Link current user to this brand to allow official preset creation.
    user_result = await db_session.execute(select(User).where(User.email == email))
    user = user_result.scalar_one()
    await grant_brand_owner_membership(db_session, brand=brand, user=user)
    await db_session.commit()
    
    # Create official preset
    preset_data = {
        "filament_id": filament.id,
        "name": "Official Preset",
        "is_official": True,
        "extruder_temp": 200.0,
        "bed_temp": 60.0,
        "print_speed": 50.0,
    }
    response = await client.post("/api/v1/presets/", json=preset_data, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["is_official"] is True
    # Official presets should be auto-approved
    assert data["moderation_status"] == "approved"


@pytest.mark.asyncio
async def test_create_official_preset_requires_verified_brand(client: AsyncClient, db_session: AsyncSession):
    """An official preset must be rejected when the brand is not verified."""
    headers, email = await _register_and_login(client, "preset-official-unverified")

    brand = Brand(name="Unverified Brand", slug="unverified-brand", active=True, verified=False)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-official-unverified",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    user_result = await db_session.execute(select(User).where(User.email == email))
    user = user_result.scalar_one()
    await grant_brand_owner_membership(db_session, brand=brand, user=user)
    await db_session.commit()

    preset_data = {
        "filament_id": filament.id,
        "name": "Official Preset",
        "is_official": True,
        "extruder_temp": 200.0,
        "bed_temp": 60.0,
        "print_speed": 50.0,
    }
    response = await client.post("/api/v1/presets/", json=preset_data, headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_OFFICIAL_VERIFIED_ONLY"


@pytest.mark.asyncio
async def test_get_preset(client: AsyncClient, db_session: AsyncSession):
    """Test getting a preset by ID."""
    # Create brand, filament, and preset
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-get",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    preset = Preset(
        filament_id=filament.id,
        name="Test Preset",
        is_official=False,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)
    
    # Get preset via API
    response = await client.get(f"/api/v1/presets/{preset.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == preset.id
    assert data["name"] == preset.name


@pytest.mark.asyncio
async def test_get_preset_not_found(client: AsyncClient):
    """Test getting non-existent preset."""
    response = await client.get("/api/v1/presets/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_presets_filter_by_filament(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering presets by filament."""
    # Create brand and filaments
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament1 = Filament(
        brand_id=brand.id,
        name="Filament 1",
        slug="filament-1",
        material_type="PLA",
        active=True,
    )
    filament2 = Filament(
        brand_id=brand.id,
        name="Filament 2",
        slug="filament-2",
        material_type="PETG",
        active=True,
    )
    db_session.add_all([filament1, filament2])
    await db_session.commit()
    await db_session.refresh(filament1)
    await db_session.refresh(filament2)
    
    # Create presets
    preset1 = Preset(
        filament_id=filament1.id,
        name="Preset 1",
        is_official=False,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    preset2 = Preset(
        filament_id=filament2.id,
        name="Preset 2",
        is_official=False,
        extruder_temp=240.0,
        bed_temp=80.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add_all([preset1, preset2])
    await db_session.commit()
    
    # Filter by filament1
    response = await client.get(f"/api/v1/presets/?filament_id={filament1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == preset1.id


@pytest.mark.asyncio
async def test_list_presets_filter_by_official(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering presets by is_official."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-official-filter",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Create official and community presets
    official_preset = Preset(
        filament_id=filament.id,
        name="Official Preset",
        is_official=True,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    community_preset = Preset(
        filament_id=filament.id,
        name="Community Preset",
        is_official=False,
        extruder_temp=195.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add_all([official_preset, community_preset])
    await db_session.commit()
    
    # Filter by official
    response = await client.get("/api/v1/presets/?is_official=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["is_official"] is True


@pytest.mark.asyncio
async def test_list_presets_search_by_name(
    client: AsyncClient, db_session: AsyncSession
):
    """Test server-side search filter by preset name."""
    brand = Brand(name="Search Brand", slug="search-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    filament = Filament(
        brand_id=brand.id,
        name="Search Filament",
        slug="search-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    alpha = Preset(
        filament_id=filament.id,
        name="Alpha Speed",
        is_official=False,
        extruder_temp=205.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    beta = Preset(
        filament_id=filament.id,
        name="Beta Quality",
        is_official=False,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add_all([alpha, beta])
    await db_session.commit()

    response = await client.get("/api/v1/presets/?search=beta")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Beta Quality"


@pytest.mark.asyncio
async def test_get_preset_recommend(client: AsyncClient, db_session: AsyncSession):
    """Test getting recommended preset for a filament."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-recommended",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Create presets with ratings
    preset1 = Preset(
        filament_id=filament.id,
        name="Preset 1",
        is_official=False,
        extruder_temp=200.0,
        bed_temp=60.0,
        rating=4.8,
        usage_count=100,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    preset2 = Preset(
        filament_id=filament.id,
        name="Preset 2",
        is_official=False,
        extruder_temp=195.0,
        bed_temp=60.0,
        rating=4.5,
        usage_count=50,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add_all([preset1, preset2])
    await db_session.commit()
    
    # Get recommended preset
    response = await client.get(f"/api/v1/presets/recommended/{filament.id}")
    assert response.status_code == 200
    data = response.json()
    assert "extruder_temp" in data
    assert "bed_temp" in data
    assert "flow_rate" in data  # material scope; print/travel speed больше не в рекомендации
    assert data["filament_id"] == filament.id


@pytest.mark.asyncio
async def test_update_preset(client: AsyncClient, db_session: AsyncSession):
    """Test updating a preset."""
    headers, email = await _register_and_login(client, "preset-update")

    # Create brand, filament, and preset
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament-update",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    user_result = await db_session.execute(select(User).where(User.email == email))
    user = user_result.scalar_one()

    preset = Preset(
        filament_id=filament.id,
        user_id=user.id,
        name="Original Name",
        is_official=False,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)
    
    # Update preset
    update_data = {
        "name": "Updated Name",
        "extruder_temp": 205.0,
    }
    response = await client.patch(
        f"/api/v1/presets/{preset.id}", json=update_data, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["extruder_temp"] == update_data["extruder_temp"]



@pytest.mark.asyncio
async def test_saving_preset_increments_usage_once(client: AsyncClient, db_session: AsyncSession):
    """usage_count is a real adoption signal: saving a preset counts it once, re-saving does not."""
    headers, _ = await _register_and_login(client, "preset-usage")

    brand = Brand(name="Usage Brand", slug="usage-brand", active=True)
    db_session.add(brand)
    await db_session.flush()

    filament = Filament(
        brand_id=brand.id,
        name="Usage PLA",
        slug="usage-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()

    preset = Preset(
        filament_id=filament.id,
        name="Usage Preset",
        is_official=True,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)

    first = await client.post(
        "/api/v1/saved-presets/", json={"preset_id": preset.id}, headers=headers
    )
    assert first.status_code == 201
    await db_session.refresh(preset)
    assert preset.usage_count == 1

    # Re-saving the same preset must not double-count (dedup on existing record).
    again = await client.post(
        "/api/v1/saved-presets/", json={"preset_id": preset.id}, headers=headers
    )
    assert again.status_code in (200, 201)
    await db_session.refresh(preset)
    assert preset.usage_count == 1


@pytest.mark.asyncio
async def test_saved_preset_unique_constraint_blocks_duplicates(db_session: AsyncSession):
    """The composite unique (user_id, preset_id) is a real DB invariant again
    (restored by usp_user_preset_unique_restore; declared in the model): a
    concurrent double-insert must fail at the database, not rely on the
    endpoint's pre-SELECT."""
    from sqlalchemy.exc import IntegrityError

    from app.models.user import User
    from app.models.user_saved_preset import UserSavedPreset

    user = User(
        email="usp-unique@example.com",
        username="usp_unique_user",
        password_hash="not-used",
        active=True,
    )
    brand = Brand(name="USP Unique Brand", slug="usp-unique-brand", active=True)
    db_session.add_all([user, brand])
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="USP Unique PLA",
        slug="usp-unique-pla",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    preset = Preset(
        filament_id=filament.id,
        name="USP Unique Preset",
        is_official=True,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db_session.add(preset)
    await db_session.commit()

    db_session.add(UserSavedPreset(user_id=user.id, preset_id=preset.id, sync=True))
    await db_session.commit()

    db_session.add(UserSavedPreset(user_id=user.id, preset_id=preset.id, sync=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
