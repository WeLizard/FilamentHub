"""Low-stock alerts: one per crossing, re-armed only by a real refill, owner-scoped."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.stock_alert_service import refresh_stock_alerts


async def _spool(db: AsyncSession, user_id: int, **fields) -> UserSpool:
    spool = UserSpool(
        user_id=user_id,
        initial_weight_g=fields.pop("initial", 500),
        used_weight_g=fields.pop("used", 0),
        state=fields.pop("state", UserSpoolState.shelf),
        source="manual",
        **fields,
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return spool


async def _alerts(db: AsyncSession, user_id: int, kind: NotificationType) -> int:
    return int(
        await db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id, Notification.type == kind
            )
        )
        or 0
    )


async def _use(client: AsyncClient, spool_id: int, grams: float) -> None:
    response = await client.post(f"/api/v1/spools/{spool_id}/use", json={"delta_weight_g": grams})
    assert response.status_code == 200, response.text


async def _rule(client: AsyncClient, **body) -> dict:
    response = await client.put("/api/v1/stock-alerts/rules", json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_spool_alert_fires_once_per_crossing_and_rearms_only_after_a_refill(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    spool = await _spool(db_session, auth_user.id)
    await _rule(auth_client, scope="spool", spool_id=spool.id, threshold_g=100)

    await _use(auth_client, spool.id, 350)  # 150 g left: above the line
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 0
    await _use(auth_client, spool.id, 100)  # 50 g left: crossed
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 1
    await _use(auth_client, spool.id, 10)  # more readings below the line stay quiet
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 1

    # A small correction around the line is not a refill.
    await auth_client.patch(f"/api/v1/spools/{spool.id}", json={"used_weight_g": 380})  # 120 g
    await _use(auth_client, spool.id, 30)  # 90 g again
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 1

    # A refilled spool re-arms; the next drop alerts once more.
    await auth_client.patch(f"/api/v1/spools/{spool.id}", json={"used_weight_g": 0})
    await _use(auth_client, spool.id, 450)
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 2

    latest = (await auth_client.get("/api/v1/stock-alerts/events")).json()
    assert latest["items"][-1]["extra_data"]["remaining_g"] == 50
    assert latest["items"][-1]["extra_data"]["threshold_g"] == 100
    after = (
        await auth_client.get("/api/v1/stock-alerts/events", params={"after_id": latest["latest_id"]})
    ).json()
    assert after["items"] == [] and after["latest_id"] == latest["latest_id"]


@pytest.mark.asyncio
async def test_a_rule_on_an_already_low_spool_and_unknown_sizes_do_not_alert(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    low = await _spool(db_session, auth_user.id, used=450)
    unknown = await _spool(db_session, auth_user.id, initial=0)
    await _rule(auth_client, scope="all", threshold_g=100)

    await _use(auth_client, low.id, 10)  # creating the rule was not a crossing
    await refresh_stock_alerts(db_session, unknown)  # size unknown: never counted as empty
    await db_session.commit()
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 0

    fresh = await _spool(db_session, auth_user.id)
    await _use(auth_client, fresh.id, 420)
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 1

    # The same reading applied twice (retry / duplicate) cannot alert twice.
    await refresh_stock_alerts(db_session, fresh)
    await db_session.commit()
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_SPOOL) == 1


@pytest.mark.asyncio
async def test_material_alert_counts_shelf_stock_of_all_its_spools_and_flags_unknown_sizes(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    brand = Brand(name="Stock Brand", slug="stock-brand", active=True)
    filament = Filament(brand=brand, name="Stock PLA", slug="stock-pla", material_type="PLA", active=True)
    db_session.add_all([brand, filament])
    await db_session.flush()
    first = await _spool(db_session, auth_user.id, filament_id=filament.id, initial=200)
    second = await _spool(db_session, auth_user.id, filament_id=filament.id, initial=200)
    await _spool(db_session, auth_user.id, filament_id=filament.id, initial=0)  # size unknown
    await _spool(db_session, auth_user.id, filament_id=filament.id, initial=500, state=UserSpoolState.active)

    await _rule(auth_client, scope="material", material_key=f"f:{filament.id}", threshold_g=150)
    await _use(auth_client, first.id, 100)  # shelf stock 300: fine
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_MATERIAL) == 0
    await _use(auth_client, second.id, 120)  # shelf stock 180: still fine
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_MATERIAL) == 0
    await _use(auth_client, second.id, 40)  # 140 < 150
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_MATERIAL) == 1
    event = (await auth_client.get("/api/v1/stock-alerts/events")).json()["items"][-1]
    assert event["extra_data"]["shelf_g"] == 140 and event["extra_data"]["unknown_count"] == 1
    # The 500 g spool in a printer is not shelf stock, so it did not hide the shortage.
    await _use(auth_client, second.id, 10)
    assert await _alerts(db_session, auth_user.id, NotificationType.LOW_STOCK_MATERIAL) == 1


@pytest.mark.asyncio
async def test_rules_and_alert_feed_are_owner_scoped(
    auth_client: AsyncClient, client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    foreign = User(email="alerts-foreign@example.com", username="alerts_foreign",
                   password_hash="unused", active=True)
    db_session.add(foreign)
    await db_session.flush()
    theirs = await _spool(db_session, foreign.id)
    refused = await auth_client.put(
        "/api/v1/stock-alerts/rules", json={"scope": "spool", "spool_id": theirs.id, "threshold_g": 100}
    )
    assert refused.status_code == 404
    unknown_material = await auth_client.put(
        "/api/v1/stock-alerts/rules", json={"scope": "material", "material_key": "f:999999"}
    )
    assert unknown_material.status_code == 404
    mismatch = await auth_client.put("/api/v1/stock-alerts/rules", json={"scope": "spool"})
    assert mismatch.status_code == 422

    default = (await auth_client.get("/api/v1/stock-alerts/rules")).json()
    assert default["default_threshold_g"] == 100 and default["rules"] == []

    rule = await _rule(auth_client, scope="all")  # threshold defaults to 100 g
    assert rule["threshold_g"] == 100
    assert (await auth_client.delete(f"/api/v1/stock-alerts/rules/{rule['id']}")).status_code == 204

    # A workstation key may read the feed, but nothing else about rules.
    key = (await auth_client.post("/api/v1/workstation-keys", json={"name": "PC"})).json()["key"]
    headers = {"Authorization": f"Bearer {key}"}
    assert (await client.get("/api/v1/stock-alerts/events", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/stock-alerts/rules", headers=headers)).status_code == 401
