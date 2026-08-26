"""Tests for QR code endpoints."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.preset import Preset, PresetModerationStatus
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from tests.conftest import accepted_legal, registration_payload


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


async def _create_official_preset(
    db: AsyncSession,
    *,
    filament_id: int,
    user_id: int,
    name: str,
) -> Preset:
    preset = Preset(
        filament_id=filament_id,
        user_id=user_id,
        name=name,
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
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def _row_count(db: AsyncSession, model: type) -> int:
    result = await db.execute(select(func.count()).select_from(model))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_redirect_qr_scan_redirects(client: AsyncClient, db_session: AsyncSession):
    """GET /{short_code} redirects to filament page."""
    filament = await _create_verified_filament(db_session)

    response = await client.get(
        f"/api/v1/qr/{filament.qr_code}",
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"] == (
        "/brands/qr-brand/filaments/qr-filament?qr=true"
    )


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
async def test_handle_qr_scan_anonymous_and_authenticated_recognize_exact_variant(
    client: AsyncClient, db_session: AsyncSession
):
    """Authentication changes neither recognition nor product state."""
    headers, user_id = await _register_and_login(client, "qr-exact")
    filament = await _create_verified_filament(db_session)
    preset = await _create_official_preset(
        db_session,
        filament_id=filament.id,
        user_id=user_id,
        name="Official Exact Preset",
    )
    start_scans = filament.scans_count
    start_usage = preset.usage_count

    anonymous = await client.post(
        f"/api/v1/qr/{filament.qr_code}/scan",
        headers={"x-country-code": "DE"},
    )
    authenticated = await client.post(
        f"/api/v1/qr/{filament.qr_code}/scan",
        headers={**headers, "x-country-code": "TR"},
    )

    assert anonymous.status_code == authenticated.status_code == 200
    anonymous_data = anonymous.json()
    authenticated_data = authenticated.json()
    for key in ("id", "slug", "brand_id", "brand_slug"):
        assert anonymous_data["filament"][key] == authenticated_data["filament"][key]
    assert anonymous_data["filament"]["id"] == filament.id
    assert anonymous_data["preset_added"] is False
    assert anonymous_data["preset"]["id"] == preset.id
    assert anonymous_data["preset_saved"] is None
    assert anonymous_data["preset_sync_enabled"] is None
    assert authenticated_data["preset_added"] is False
    assert authenticated_data["preset"]["id"] == preset.id
    assert authenticated_data["preset_saved"] is False
    assert authenticated_data["preset_sync_enabled"] is None

    await db_session.refresh(filament)
    await db_session.refresh(preset)
    assert filament.scans_count == start_scans + 2
    assert preset.usage_count == start_usage

    events = await db_session.execute(
        select(FilamentAnalyticsEvent)
        .where(
            FilamentAnalyticsEvent.filament_id == filament.id,
            FilamentAnalyticsEvent.event_type == "qr_scan",
        )
        .order_by(FilamentAnalyticsEvent.id)
    )
    assert [event.country for event in events.scalars()] == ["DE", "TR"]
    assert await _row_count(db_session, UserSavedPreset) == 0
    assert await _row_count(db_session, UserSpool) == 0
    assert await _row_count(db_session, MaterialSlotAssignment) == 0

    desired = await client.get("/api/v1/auth/my-presets", headers=headers)
    assert desired.status_code == 200
    assert desired.json()["total"] == 0


@pytest.mark.asyncio
async def test_handle_qr_scan_authenticated_no_preset(
    client: AsyncClient, db_session: AsyncSession
):
    """Authenticated scan without official preset: preset_added=False."""
    headers, _ = await _register_and_login(client, "qr-auth")
    filament = await _create_verified_filament(db_session)

    response = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["preset_added"] is False
    assert data["preset"] is None
    assert data["preset_saved"] is None
    assert data["preset_sync_enabled"] is None


@pytest.mark.asyncio
async def test_handle_qr_scan_reports_existing_library_state_without_changing_it(
    client: AsyncClient, db_session: AsyncSession
):
    """Recognition exposes saved/sync state but never rewrites either value."""
    headers, user_id = await _register_and_login(client, "qr-saved-state")
    filament = await _create_verified_filament(db_session)
    preset = await _create_official_preset(
        db_session,
        filament_id=filament.id,
        user_id=user_id,
        name="Official Saved-State Preset",
    )
    start_usage = preset.usage_count
    saved_preset = UserSavedPreset(user_id=user_id, preset_id=preset.id, sync=False)
    db_session.add(saved_preset)
    await db_session.commit()

    sync_off = await client.post(
        f"/api/v1/qr/{filament.qr_code}/scan", headers=headers
    )
    assert sync_off.status_code == 200
    assert sync_off.json()["preset_saved"] is True
    assert sync_off.json()["preset_sync_enabled"] is False

    saved_preset.sync = True
    await db_session.commit()
    sync_on = await client.post(
        f"/api/v1/qr/{filament.qr_code}/scan", headers=headers
    )
    assert sync_on.status_code == 200
    assert sync_on.json()["preset_saved"] is True
    assert sync_on.json()["preset_sync_enabled"] is True

    await db_session.refresh(preset)
    await db_session.refresh(saved_preset)
    assert preset.usage_count == start_usage
    assert saved_preset.sync is True
    assert await _row_count(db_session, UserSavedPreset) == 1
    assert await _row_count(db_session, UserSpool) == 0
    assert await _row_count(db_session, MaterialSlotAssignment) == 0


@pytest.mark.asyncio
async def test_handle_qr_scan_repeated_requests_only_record_analytics(
    client: AsyncClient, db_session: AsyncSession
):
    """Repeated scans do not turn recognition into inventory or desired state."""
    headers, user_id = await _register_and_login(client, "qr-repeat")
    filament = await _create_verified_filament(db_session)
    preset = await _create_official_preset(
        db_session,
        filament_id=filament.id,
        user_id=user_id,
        name="Official Repeat Preset",
    )
    start_scans = filament.scans_count
    start_usage = preset.usage_count

    r1 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    r2 = await client.post(f"/api/v1/qr/{filament.qr_code}/scan", headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["preset_added"] is False
    assert r2.json()["preset_added"] is False
    assert r1.json()["preset"]["id"] == preset.id
    assert r2.json()["preset"]["id"] == preset.id
    assert r1.json()["preset_saved"] is False
    assert r2.json()["preset_saved"] is False
    assert r1.json()["preset_sync_enabled"] is None
    assert r2.json()["preset_sync_enabled"] is None

    await db_session.refresh(filament)
    await db_session.refresh(preset)
    assert filament.scans_count == start_scans + 2
    assert preset.usage_count == start_usage
    event_count = await db_session.execute(
        select(func.count())
        .select_from(FilamentAnalyticsEvent)
        .where(
            FilamentAnalyticsEvent.filament_id == filament.id,
            FilamentAnalyticsEvent.event_type == "qr_scan",
        )
    )
    assert event_count.scalar_one() == 2
    assert await _row_count(db_session, UserSavedPreset) == 0
    assert await _row_count(db_session, UserSpool) == 0
    assert await _row_count(db_session, MaterialSlotAssignment) == 0


@pytest.mark.asyncio
async def test_handle_qr_scan_concurrent_requests_create_no_product_state(tmp_path):
    """Concurrent authenticated recognition only appends scan analytics."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.security import create_access_token
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app
    from app.models.user import User

    database_path = (tmp_path / "qr-concurrent.db").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    had_db_override = get_db in app.dependency_overrides
    previous_db_override = app.dependency_overrides.get(get_db)
    limiter_was_enabled = app.state.limiter.enabled

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as setup_db:
            user = User(
                email="qr-concurrent@example.com",
                username="qr_concurrent",
                password_hash="unused",
                active=True,
                email_verified=True,
                **accepted_legal(),
            )
            brand = Brand(
                name="Concurrent QR Brand",
                slug="concurrent-qr-brand",
                active=True,
                verified=True,
            )
            setup_db.add_all([user, brand])
            await setup_db.commit()
            await setup_db.refresh(user)
            await setup_db.refresh(brand)

            filament = Filament(
                brand_id=brand.id,
                name="Concurrent QR Filament",
                slug="concurrent-qr-filament",
                material_type="PLA",
                active=True,
                qr_code="concurrent-qr-code",
            )
            setup_db.add(filament)
            await setup_db.commit()
            await setup_db.refresh(filament)
            preset = await _create_official_preset(
                setup_db,
                filament_id=filament.id,
                user_id=user.id,
                name="Official Concurrent Preset",
            )
            filament_id = filament.id
            preset_id = preset.id
            short_code = filament.qr_code
            token = create_access_token({"sub": user.email})

        async def override_get_db():
            async with session_factory() as request_db:
                yield request_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.limiter.enabled = False
        transport = ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=transport, base_url="http://test") as test_client:
            responses = await asyncio.gather(
                test_client.post(f"/api/v1/qr/{short_code}/scan", headers=headers),
                test_client.post(f"/api/v1/qr/{short_code}/scan", headers=headers),
            )

        assert [response.status_code for response in responses] == [200, 200]
        assert [response.json()["filament"]["id"] for response in responses] == [
            filament_id,
            filament_id,
        ]
        assert [response.json()["preset_added"] for response in responses] == [
            False,
            False,
        ]
        assert [response.json()["preset_saved"] for response in responses] == [
            False,
            False,
        ]
        assert [response.json()["preset_sync_enabled"] for response in responses] == [
            None,
            None,
        ]
        assert [response.json()["preset"]["id"] for response in responses] == [
            preset_id,
            preset_id,
        ]

        async with session_factory() as verification_db:
            assert await _row_count(verification_db, UserSavedPreset) == 0
            assert await _row_count(verification_db, UserSpool) == 0
            assert await _row_count(verification_db, MaterialSlotAssignment) == 0
            events = await verification_db.execute(
                select(func.count())
                .select_from(FilamentAnalyticsEvent)
                .where(
                    FilamentAnalyticsEvent.filament_id == filament_id,
                    FilamentAnalyticsEvent.event_type == "qr_scan",
                )
            )
            assert events.scalar_one() == 2
    finally:
        if had_db_override:
            app.dependency_overrides[get_db] = previous_db_override
        else:
            app.dependency_overrides.pop(get_db, None)
        app.state.limiter.enabled = limiter_was_enabled
        await engine.dispose()


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
