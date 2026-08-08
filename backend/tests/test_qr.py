"""Tests for QR code endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from tests.conftest import registration_payload


async def _register_and_login(client: AsyncClient, suffix: str) -> tuple[dict, int]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    reg = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email, username=f"user_{suffix}", password=password
        ),
    )
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    return headers, me.json()["id"]


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


def test_a_printed_code_reads_back_at_every_offered_size():
    """A code a brand prints must decode; the sizes are what they are offered."""
    import cv2
    import numpy as np
    from PIL import Image

    from app.services.qr_service import _qr_target_url, generate_qr_code_image

    detector = cv2.QRCodeDetector()
    expected = _qr_target_url("FH-TST-001")

    for size in (300, 600, 1200):
        image = Image.open(generate_qr_code_image("FH-TST-001", size=size)).convert("L")
        # Размер обязан быть ровно запрошенным: бренд ставит код в макет.
        assert image.size == (size, size)
        assert detector.detectAndDecode(np.array(image))[0] == expected


def test_a_code_stays_readable_when_printed_small():
    """A spool sticker is not a poster; the code has to survive being tiny."""
    import cv2
    import numpy as np
    from PIL import Image

    from app.services.qr_service import _qr_target_url, generate_qr_code_image

    detector = cv2.QRCodeDetector()
    expected = _qr_target_url("FH-TST-001")
    large = Image.open(generate_qr_code_image("FH-TST-001", size=1200)).convert("L")

    small = large.resize((120, 120), Image.NEAREST)
    assert detector.detectAndDecode(np.array(small))[0] == expected


def test_the_branded_code_still_decodes_at_every_offered_size():
    """The mark is paid for by redundancy — prove it, do not assume it.

    The share of the code the mark covers says nothing on its own: correction
    works over codewords, not over picture area. So the only honest check is a
    decoder against the sizes a brand is actually offered.
    """
    import cv2
    import numpy as np
    from PIL import Image

    from app.services.qr_service import _qr_target_url, generate_branded_qr_code_image

    detector = cv2.QRCodeDetector()
    expected = _qr_target_url("FH-TST-001")
    master = Image.open(generate_branded_qr_code_image("FH-TST-001", size=1200))

    for size in (1200, 600, 300, 120):
        scaled = np.array(master.resize((size, size), Image.LANCZOS).convert("L"))
        assert detector.detectAndDecode(scaled)[0] == expected, f"unreadable at {size}px"


def test_the_mark_leaves_the_finder_patterns_alone():
    """Cover a corner and no scanner can orient the code at all."""
    import numpy as np
    from PIL import Image

    from app.services.qr_service import generate_branded_qr_code_image, generate_qr_code_image

    # Compared as shapes, not as shades: the mark draws its modules in near-black
    # rather than pure black, and that difference is not what this test is about.
    branded = np.array(
        Image.open(generate_branded_qr_code_image("FH-TST-001", size=1200)).convert("L")
    ) > 128
    plain = np.array(
        Image.open(generate_qr_code_image("FH-TST-001", size=1200, error_correction="H")).convert("L")
    ) > 128
    # The three finder patterns sit in the corners; the mark lives in the middle
    # and must not have touched them.
    corner = branded.shape[0] // 4
    for row, column in ((slice(0, corner), slice(0, corner)),
                        (slice(0, corner), slice(-corner, None)),
                        (slice(-corner, None), slice(0, corner))):
        assert np.array_equal(branded[row, column], plain[row, column])


def test_the_branded_vector_matches_the_branded_picture():
    """Packaging takes the vector, so it must be the same code, not a lookalike.

    The window is counted once for both formats; if the two ever disagree, a
    brand prints something we never showed them on screen.
    """
    import re

    from app.services.qr_service import (
        BRANDED_MARK_SHARE,
        _branded_layout,
        generate_branded_qr_code_svg,
    )

    matrix, window, low = _branded_layout("FH-TST-001", BRANDED_MARK_SHARE)
    svg = generate_branded_qr_code_svg("FH-TST-001").getvalue().decode("utf-8")

    total = len(matrix)
    assert f'viewBox="0 0 {total} {total}"' in svg
    # Никакой растровой вставки внутри вектора: типография масштабирует его как есть.
    assert "<image" not in svg and "base64" not in svg

    expected_modules = sum(
        1
        for row_index, row in enumerate(matrix)
        for column_index, is_dark in enumerate(row)
        if is_dark and not (low <= row_index < low + window and low <= column_index < low + window)
    )
    assert len(re.findall(r"M\d+,\d+h1v1h-1z", svg)) == expected_modules


def test_print_shops_can_take_the_code_as_vector():
    """Packaging is printed at whatever size the brand wants."""
    from app.services.qr_service import generate_qr_code_svg

    svg = generate_qr_code_svg("FH-TST-001").getvalue().decode("utf-8")
    assert svg.startswith("<?xml")
    assert "<svg" in svg
    assert "<path" in svg
