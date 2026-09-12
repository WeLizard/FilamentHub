"""Owned spool feed pagination and physical-instance identity regressions."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


async def _filament(db: AsyncSession) -> Filament:
    brand = Brand(name="Feed Brand", slug="feed-brand", verified=True, active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Same QR product",
        slug="same-qr-product",
        material_type="PLA",
        color_name="Blue",
        color_hex="0066CC",
        qr_code="same-product-qr",
        diameter=1.75,
        density=1.24,
        spool_weight=1000.0,
        active=True,
    )
    db.add(filament)
    await db.flush()
    return filament


async def _spool(
    db: AsyncSession,
    user_id: int,
    *,
    filament_id: int | None = None,
    state: UserSpoolState = UserSpoolState.shelf,
    created_at: datetime,
    initial: float = 1000,
    used: float = 0,
) -> UserSpool:
    spool = UserSpool(
        user_id=user_id,
        filament_id=filament_id,
        state=state,
        source="qr" if filament_id else "manual",
        initial_weight_g=initial,
        used_weight_g=used,
        created_at=created_at,
    )
    db.add(spool)
    await db.flush()
    return spool


@pytest.mark.asyncio
async def test_feed_is_tenant_scoped_stable_and_keeps_same_qr_spools_distinct(
    auth_client, db_session: AsyncSession, auth_user: User
):
    now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    filament = await _filament(db_session)
    first = await _spool(db_session, auth_user.id, filament_id=filament.id, created_at=now)
    second = await _spool(db_session, auth_user.id, filament_id=filament.id, created_at=now)
    older = await _spool(
        db_session,
        auth_user.id,
        filament_id=filament.id,
        created_at=now - timedelta(minutes=1),
        state=UserSpoolState.empty,
        used=1000,
    )
    stranger = User(
        email="spool-feed-stranger@example.com", username="spoolfeedstranger", password_hash="x"
    )
    db_session.add(stranger)
    await db_session.flush()
    foreign = await _spool(db_session, stranger.id, filament_id=filament.id, created_at=now)
    await db_session.commit()

    page = await auth_client.get(
        "/api/v1/spools/feed",
        params={"limit": 1, "state_group": "available", "filament_id": filament.id},
    )
    assert page.status_code == 200
    body = page.json()
    assert [item["id"] for item in body["items"]] == [second.id]
    assert body["summary"]["total"] == 3
    assert body["summary"]["state_counts"] == {"active": 0, "shelf": 2, "archived": 0, "empty": 1}
    assert body["summary"]["available_remaining_weight_g"] == 2000

    inserted = await _spool(
        db_session, auth_user.id, filament_id=filament.id, created_at=now + timedelta(minutes=1)
    )
    await db_session.commit()
    next_page = await auth_client.get(
        "/api/v1/spools/feed",
        params={
            "limit": 2,
            "state_group": "available",
            "filament_id": filament.id,
            "cursor": body["next_cursor"],
        },
    )
    assert next_page.status_code == 200
    next_ids = [item["id"] for item in next_page.json()["items"]]
    assert next_ids == [first.id]
    assert inserted.id not in next_ids
    assert foreign.id not in next_ids
    assert older.id not in next_ids


@pytest.mark.asyncio
async def test_feed_validates_cursor_filters_and_owned_detail(
    auth_client, db_session: AsyncSession, auth_user: User
):
    now = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    owned = await _spool(db_session, auth_user.id, created_at=now)
    stranger = User(
        email="spool-detail-stranger@example.com", username="spooldetailstranger", password_hash="x"
    )
    db_session.add(stranger)
    await db_session.flush()
    foreign = await _spool(db_session, stranger.id, created_at=now)
    await db_session.commit()

    detail = await auth_client.get(f"/api/v1/spools/{owned.id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == owned.id
    assert (await auth_client.get(f"/api/v1/spools/{foreign.id}")).status_code == 404

    invalid_cursor = await auth_client.get("/api/v1/spools/feed", params={"cursor": "broken"})
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["detail"]["code"] == "ERR_SPOOL_CURSOR_INVALID"
    invalid_filters = await auth_client.get(
        "/api/v1/spools/feed", params={"state": "shelf", "state_group": "available"}
    )
    assert invalid_filters.status_code == 422
    assert invalid_filters.json()["detail"]["code"] == "ERR_SPOOL_FEED_FILTER_INVALID"

    legacy = await auth_client.get("/api/v1/spools")
    assert legacy.status_code == 200
    assert [item["id"] for item in legacy.json()] == [owned.id]
