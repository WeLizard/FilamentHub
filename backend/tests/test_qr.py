"""Tests for QR code endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus


async def _register_and_login(client: AsyncClient, suffix: str) -> tuple[dict, int]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "username": f"user_{suffix}",
        "password": password, "role": "user",
    })
    assert reg.status_code == 201
    user_id = reg.json()["id"]
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, user_id


async def _create_verified_filament(db: AsyncSession) -> Filament:
    brand = Brand(name="QR Brand", slug="qr-brand", active=True, verified=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    filament = Filament(
        brand_id=brand.id, name="QR Filament",
        slug="qr-filament", material_type="PLA", active=True,
        qr_code="test-qr-abc123",
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


async def _create_unverified_filament(db: AsyncSession) -> Filament:
    brand = Brand(name="Unverified Brand", slug="unverified-brand", active=True, verified=False)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    filament = Filament(
        brand_id=brand.id, name="Unverified Filament",
        slug="unverified-filament", material_type="PETG", active=True,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


@pytest.mark.asyncio
async def test_redirect_qr_scan_redirects(client: AsyncClient, db_session: AsyncSession):
    """GET /{short_code} redirects to filament page."""
    filament = await _create_verified_filament(db_session)
    initial_scans = filament.scans_count

    response = await client.get(
        f"/api/v1/qr/{filament.qr_code}",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert f"/filaments/{filament.id}" in response.headers["location"]


@pytest.mark.asyncio
async def test_redirect_qr_increments_scan_count(client: AsyncClient, db_session: AsyncSession):
    """Redirect increments scans_count on the filament."""
    filament = await _create_verified_filament(db_session)
    initial_scans = filament.scans_count

    await client.get(f"/api/v1/qr/{filament.qr_code}", follow_redirects=False)

    await db_session.refresh(filament)
    assert filament.scans_count == initial_scans + 1


@pytest.mark.asyncio
async def test_redirect_qr_not_found(client: AsyncClient):
    """Unknown short code returns 404."""
    response = await client.get("/api/v1/qr/no-such-code", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_handle_qr_scan_anonymous(client: AsyncClient, db_session: AsyncSession):
    """Anonymous scan: increments counter, no preset added."""
    filament = await _create_verified_filament(db_session)

    response = await client.post(f"/api/v1/qr/{filament.qr_code}/scan")
    assert response.status_code == 200
    data = response.json()
    assert data["preset_added"] is False
    assert data["preset"] is None
    assert data["filament"]["id"] == filament.id


@pytest.mark.asyncio
async def test_handle_qr_scan_authenticated_no_preset(client: AsyncClient, db_session: AsyncSession):
    """Authenticated scan without official preset: preset_added=False."""
    headers, _ = await _register_and_login(client, "qr-auth")
    filament = await _create_verified_filament(db_session)

    response = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["preset_added"] is False


@pytest.mark.asyncio
async def test_handle_qr_scan_adds_official_preset(client: AsyncClient, db_session: AsyncSession):
    """Authenticated scan auto-adds official preset to user profile."""
    headers, user_id = await _register_and_login(client, "qr-preset")
    filament = await _create_verified_filament(db_session)

    # Create official preset for filament
    preset = Preset(
        filament_id=filament.id,
        user_id=user_id,
        name="Official QR Preset",
        is_official=True,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        extruder_temp=210.0,
        bed_temp=65.0,
        flow_rate=100.0,
        fan_speed=100,
        retraction_length=1.0,
        retraction_speed=45.0,
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)

    response = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["preset_added"] is True
    assert data["preset"]["id"] == preset.id


@pytest.mark.asyncio
async def test_handle_qr_scan_no_duplicate_preset(client: AsyncClient, db_session: AsyncSession):
    """Scanning twice does not add preset twice."""
    headers, user_id = await _register_and_login(client, "qr-nodup")
    filament = await _create_verified_filament(db_session)

    preset = Preset(
        filament_id=filament.id,
        user_id=user_id,
        name="Official QR Preset 2",
        is_official=True,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        extruder_temp=210.0,
        bed_temp=65.0,
        flow_rate=100.0,
        fan_speed=100,
        retraction_length=1.0,
        retraction_speed=45.0,
    )
    db_session.add(preset)
    await db_session.commit()

    r1 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert r1.json()["preset_added"] is True

    r2 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert r2.json()["preset_added"] is False  # already in profile


@pytest.mark.asyncio
async def test_handle_qr_scan_counts_and_dedups(client: AsyncClient, db_session: AsyncSession):
    """Repeat scans always register the scan and never duplicate the saved
    preset — the scan commit is separate from the racy auto-save."""
    from app.models.user_saved_preset import UserSavedPreset

    headers, user_id = await _register_and_login(client, "qr-count")
    filament = await _create_verified_filament(db_session)
    start_scans = filament.scans_count

    preset = Preset(
        filament_id=filament.id, user_id=user_id, name="Official Count Preset",
        is_official=True, active=True, moderation_status=PresetModerationStatus.APPROVED,
        extruder_temp=210.0, bed_temp=65.0,
    )
    db_session.add(preset)
    await db_session.commit()
    await db_session.refresh(preset)

    r1 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    r2 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["preset_added"] is True
    assert r2.json()["preset_added"] is False

    await db_session.refresh(filament)
    assert filament.scans_count == start_scans + 2

    saved = await db_session.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user_id, UserSavedPreset.preset_id == preset.id
        )
    )
    assert len(saved.scalars().all()) == 1


@pytest.mark.asyncio
async def test_handle_qr_scan_insert_race_returns_ok(
    client: AsyncClient, db_session: AsyncSession, monkeypatch
):
    """If a concurrent scan inserts the same (user, preset) first, our insert
    hits the restored unique index. The endpoint must roll back that insert and
    still return 200 with the scan counted — not a 500."""
    from sqlalchemy.exc import IntegrityError

    headers, user_id = await _register_and_login(client, "qr-race")
    filament = await _create_verified_filament(db_session)
    start_scans = filament.scans_count

    preset = Preset(
        filament_id=filament.id, user_id=user_id, name="Official Race Preset",
        is_official=True, active=True, moderation_status=PresetModerationStatus.APPROVED,
        extruder_temp=210.0, bed_temp=65.0,
    )
    db_session.add(preset)
    await db_session.commit()

    # Force the second commit (the saved-preset insert; the first is the scan
    # counter) to fail as if a concurrent scan won the unique race.
    real_commit = db_session.commit
    calls = {"n": 0}

    async def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 2:
            raise IntegrityError("duplicate saved preset", None, Exception("unique"))
        return await real_commit()

    monkeypatch.setattr(db_session, "commit", flaky_commit)

    response = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert response.status_code == 200
    assert response.json()["preset_added"] is False

    monkeypatch.undo()
    await db_session.refresh(filament)
    assert filament.scans_count == start_scans + 1  # scan committed despite the race


@pytest.mark.asyncio
async def test_get_qr_code_image_unverified_brand(client: AsyncClient, db_session: AsyncSession):
    """Generating QR for unverified brand returns 403."""
    filament = await _create_unverified_filament(db_session)

    response = await client.get(f"/api/v1/qr/filaments/{filament.id}/qr-code")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_QR_VERIFIED_ONLY"


@pytest.mark.asyncio
async def test_get_qr_code_image_filament_not_found(client: AsyncClient):
    """404 when requesting QR image for non-existent filament."""
    response = await client.get("/api/v1/qr/filaments/99999/qr-code")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_download_qr_requires_auth(client: AsyncClient, db_session: AsyncSession):
    """QR download endpoint requires authentication."""
    filament = await _create_verified_filament(db_session)

    response = await client.get(f"/api/v1/qr/filaments/{filament.id}/qr-code/download")
    assert response.status_code == 401
