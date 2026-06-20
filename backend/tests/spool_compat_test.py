"""Tests for spool_compat endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.spool_compat import _filament_payload, _filament_temps
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


async def _seed_spool_context(db: AsyncSession) -> tuple[User, UserSpool]:
    user = User(
        email="spool-compat-test@example.com",
        username="spool_compat_test_user",
        password_hash="not-used-in-this-test",
        api_key="spool_compat_test_api_key",
        active=True,
    )
    brand = Brand(name="Spool Compat Test Brand", slug="spool-compat-test-brand", verified=True, active=True)
    filament = Filament(
        brand=brand,
        name="Spool Compat Test PLA Black",
        slug="spool-compat-test-pla-black",
        material_type="PLA",
        color_name="Black",
        color_hex="#111111",
        diameter=1.75,
        density=1.24,
        spool_weight=1000.0,
        active=True,
    )
    spool = UserSpool(
        user=user,
        filament=filament,
        initial_weight_g=1000.0,
        used_weight_g=100.0,
        state=UserSpoolState.active,
        source="manual",
        lot_nr="LOT-1",
        comment="seed spool",
    )
    db.add_all([user, brand, filament, spool])
    await db.commit()
    await db.refresh(user)
    await db.refresh(spool)
    return user, spool


@pytest.mark.asyncio
async def test_spool_compat_sync_legacy_deprecated(client: AsyncClient):
    """Legacy /sync endpoint should remain available but marked deprecated."""
    response = await client.get("/api/v1/spool_compat/sync")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "deprecated"
    assert "v1" in data["message"].lower()


@pytest.mark.asyncio
async def test_spool_compat_v1_health_info(client: AsyncClient):
    """Health/info endpoints should be available for compatibility checks."""
    health = await client.get("/api/v1/spool_compat/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    info = await client.get("/api/v1/spool_compat/v1/info")
    assert info.status_code == 200
    assert "version" in info.json()


@pytest.mark.asyncio
async def test_spool_compat_v1_requires_api_key(client: AsyncClient):
    """Scoped spool endpoints should reject requests without a valid key."""
    response = await client.get("/api/v1/spool_compat/invalid/v1/spool")
    assert response.status_code == 401
    assert "message" in response.json()


@pytest.mark.asyncio
async def test_spool_compat_v1_list_get_use_spool(client: AsyncClient, db_session: AsyncSession):
    """Compatibility spool flow: list -> get -> use."""
    user, spool = await _seed_spool_context(db_session)

    list_response = await client.get(f"/api/v1/spool_compat/{user.api_key}/v1/spool")
    assert list_response.status_code == 200
    assert list_response.headers.get("x-total-count") == "1"
    list_data = list_response.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == spool.id
    assert list_data[0]["filament"]["material"] == "PLA"

    get_response = await client.get(f"/api/v1/spool_compat/{user.api_key}/v1/spool/{spool.id}")
    assert get_response.status_code == 200
    assert get_response.json()["used_weight"] == 100.0

    use_response = await client.put(
        f"/api/v1/spool_compat/{user.api_key}/v1/spool/{spool.id}/use",
        json={"use_weight": 50},
    )
    assert use_response.status_code == 200
    used_weight = use_response.json()["used_weight"]
    assert used_weight == pytest.approx(150.0, rel=1e-6)


def _approved_preset(**overrides) -> Preset:
    base = {
        "name": "test preset",
        "extruder_temp": 240.0,
        "bed_temp": 80.0,
        "print_speed": 50.0,
        "is_official": True,
        "active": True,
        "moderation_status": PresetModerationStatus.APPROVED,
    }
    base.update(overrides)
    return Preset(**base)


def test_filament_temps_uses_representative_preset():
    """Gate map temps must come from the filament's preset, not be None."""
    filament = Filament(name="PETG X", slug="petg-x", material_type="PETG")
    filament.presets = [
        _approved_preset(extruder_temp=245.0, bed_temp=85.0, rating=4.8, usage_count=10),
        _approved_preset(extruder_temp=230.0, bed_temp=70.0, rating=3.0, usage_count=2),
    ]
    assert _filament_temps(filament) == (245.0, 85.0)


def test_filament_temps_prefers_official_over_user_preset():
    filament = Filament(name="PLA Y", slug="pla-y", material_type="PLA")
    filament.presets = [
        _approved_preset(is_official=False, extruder_temp=200.0, bed_temp=55.0, rating=5.0),
        _approved_preset(is_official=True, extruder_temp=215.0, bed_temp=60.0, rating=4.0),
    ]
    assert _filament_temps(filament) == (215.0, 60.0)


def test_filament_temps_falls_back_to_material_defaults():
    """No preset → material defaults so Happy Hare never receives None."""
    filament = Filament(name="PETG Z", slug="petg-z", material_type="PETG")
    filament.presets = []
    extruder, bed = _filament_temps(filament)
    assert extruder == 240.0
    assert bed == 80.0


def test_filament_temps_ignores_unapproved_and_inactive_presets():
    filament = Filament(name="PLA W", slug="pla-w", material_type="PLA")
    filament.presets = [
        _approved_preset(moderation_status=PresetModerationStatus.PENDING, extruder_temp=999.0),
        _approved_preset(active=False, extruder_temp=999.0),
    ]
    # All candidates filtered out → material defaults for PLA.
    assert _filament_temps(filament) == (215.0, 60.0)


def test_filament_payload_never_emits_none_temps():
    """The Spoolman payload fields HH parses with int() must be numeric."""
    filament = Filament(name="ABS Q", slug="abs-q", material_type="ABS")
    filament.presets = []
    payload = _filament_payload(filament, fallback_id=1)
    assert payload["settings_extruder_temp"] is not None
    assert payload["settings_bed_temp"] is not None

