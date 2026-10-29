"""Batch spool creation: idempotent replay, exact price split and atomic failure."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset_usage_event import PresetUsageEvent
from app.models.spool_batch_receipt import SpoolBatchReceipt
from app.models.user import User
from app.models.user_limit import UserLimit
from app.models.user_spool import UserSpool
from app.services import spool_batch_service


async def _filament(db: AsyncSession) -> Filament:
    brand = Brand(name="Batch Brand", slug="batch-brand", verified=True, active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Batch PLA",
        slug="batch-pla",
        material_type="PLA",
        color_name="Red",
        color_hex="CC0000",
        diameter=1.75,
        density=1.24,
        spool_weight=1000.0,
        active=True,
    )
    db.add(filament)
    await db.commit()
    return filament


def _body(filament_id: int | None, key: str = "spool-batch-key-0001", **overrides) -> dict:
    body = {
        "idempotency_key": key,
        "quantity": 3,
        "filament_id": filament_id,
        "initial_weight_g": 1000,
    }
    body.update(overrides)
    return body


async def _count(db: AsyncSession, model) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


@pytest.mark.asyncio
async def test_replay_returns_same_spools_and_creates_nothing(
    auth_client, db_session: AsyncSession
):
    filament = await _filament(db_session)
    body = _body(filament.id, price="10.50", currency="RUB")

    first = await auth_client.post("/api/v1/spools/batch", json=body)
    second = await auth_client.post("/api/v1/spools/batch", json=body)

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["replayed"] is False and second.json()["replayed"] is True
    ids = [spool["id"] for spool in first.json()["spools"]]
    assert len(set(ids)) == 3
    assert [spool["id"] for spool in second.json()["spools"]] == ids
    assert await _count(db_session, UserSpool) == 3
    assert await _count(db_session, SpoolBatchReceipt) == 1


@pytest.mark.asyncio
async def test_same_key_with_different_payload_conflicts(auth_client, db_session: AsyncSession):
    filament = await _filament(db_session)
    first = await auth_client.post("/api/v1/spools/batch", json=_body(filament.id))
    assert first.status_code == 201

    changed = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, quantity=4)
    )

    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "ERR_SPOOL_BATCH_KEY_CONFLICT"
    assert await _count(db_session, UserSpool) == 3


@pytest.mark.asyncio
async def test_unknown_filament_leaves_no_spools_or_receipt(
    auth_client, db_session: AsyncSession
):
    response = await auth_client.post("/api/v1/spools/batch", json=_body(999_999))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_NOT_FOUND"
    assert await _count(db_session, UserSpool) == 0
    assert await _count(db_session, SpoolBatchReceipt) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("currency", "price", "expected"),
    [
        ("RUB", "100.00", [33.34, 33.33, 33.33]),
        ("JPY", "1000", [334, 333, 333]),
    ],
)
async def test_total_price_is_split_exactly_in_minor_units(
    auth_client, db_session: AsyncSession, currency, price, expected
):
    filament = await _filament(db_session)

    response = await auth_client.post(
        "/api/v1/spools/batch",
        json=_body(filament.id, price_mode="total", price=price, currency=currency),
    )

    assert response.status_code == 201
    data = response.json()
    assert [spool["price"] for spool in data["spools"]] == expected
    assert float(data["total_price"]) == float(price)
    receipt = await db_session.scalar(select(SpoolBatchReceipt))
    assert float(receipt.total_price) == float(price)


@pytest.mark.asyncio
async def test_per_spool_price_is_kept_on_every_spool(auth_client, db_session: AsyncSession):
    filament = await _filament(db_session)

    response = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, price="12.50", currency="USD")
    )

    data = response.json()
    assert [spool["price"] for spool in data["spools"]] == [12.5, 12.5, 12.5]
    assert float(data["total_price"]) == 37.5


@pytest.mark.asyncio
async def test_unknown_price_stays_null_and_explicit_zero_stays_zero(
    auth_client, db_session: AsyncSession
):
    filament = await _filament(db_session)

    unknown = await auth_client.post("/api/v1/spools/batch", json=_body(filament.id, "unknown-key-1"))
    zero = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, "zero-price-key-1", price="0")
    )

    assert [s["price"] for s in unknown.json()["spools"]] == [None, None, None]
    assert unknown.json()["total_price"] is None
    assert [s["price"] for s in zero.json()["spools"]] == [0.0, 0.0, 0.0]
    assert float(zero.json()["total_price"]) == 0.0


@pytest.mark.asyncio
async def test_quantity_above_limit_is_rejected(auth_client, db_session: AsyncSession):
    filament = await _filament(db_session)

    response = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, quantity=101)
    )

    assert response.status_code == 422
    assert await _count(db_session, UserSpool) == 0


@pytest.mark.asyncio
async def test_retry_after_deleting_a_spool_does_not_recreate_it(
    auth_client, db_session: AsyncSession
):
    filament = await _filament(db_session)
    body = _body(filament.id)
    first = await auth_client.post("/api/v1/spools/batch", json=body)
    ids = [spool["id"] for spool in first.json()["spools"]]
    deleted = await auth_client.delete(f"/api/v1/spools/{ids[0]}")
    assert deleted.status_code in (200, 204)

    retry = await auth_client.post("/api/v1/spools/batch", json=body)

    assert retry.json()["replayed"] is True
    assert [spool["id"] for spool in retry.json()["spools"]] == ids[1:]
    assert await _count(db_session, UserSpool) == 2


@pytest.mark.asyncio
async def test_opening_usage_event_is_recorded_for_every_spool(
    auth_client, db_session: AsyncSession, auth_user: User
):
    filament = await _filament(db_session)

    response = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, used_weight_g=250)
    )

    assert response.status_code == 201
    assert await _count(db_session, PresetUsageEvent) == 3
    assert all(s["remaining_weight_g"] == 750 for s in response.json()["spools"])


@pytest.mark.asyncio
async def test_concurrent_duplicate_hits_unique_key_and_replays(
    auth_client, db_session: AsyncSession, monkeypatch
):
    filament = await _filament(db_session)
    body = _body(filament.id)
    first = await auth_client.post("/api/v1/spools/batch", json=body)

    real_find = spool_batch_service._find_receipt
    calls = {"count": 0}

    async def miss_first_lookup(db, user_id, key_digest):
        calls["count"] += 1
        return None if calls["count"] == 1 else await real_find(db, user_id, key_digest)

    monkeypatch.setattr(spool_batch_service, "_find_receipt", miss_first_lookup)
    racing = await auth_client.post("/api/v1/spools/batch", json=body)

    assert racing.status_code == 201
    assert racing.json()["replayed"] is True
    assert [x["id"] for x in racing.json()["spools"]] == [x["id"] for x in first.json()["spools"]]
    assert await _count(db_session, UserSpool) == 3


@pytest.mark.asyncio
async def test_default_limit_rejects_21_and_creates_nothing(
    auth_client, db_session: AsyncSession
):
    filament = await _filament(db_session)

    response = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, quantity=21)
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "ERR_SPOOL_BATCH_LIMIT",
        "params": {"limit": 20},
    }
    assert await _count(db_session, UserSpool) == 0
    assert await _count(db_session, SpoolBatchReceipt) == 0


@pytest.mark.asyncio
async def test_account_limit_row_raises_the_limit_and_is_reported(
    auth_client, db_session: AsyncSession, auth_user: User
):
    filament = await _filament(db_session)
    assert (await auth_client.get("/api/v1/spools/batch-limit")).json() == {"limit": 20}
    db_session.add(UserLimit(user_id=auth_user.id, spool_batch_limit=50))
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/spools/batch", json=_body(filament.id, quantity=21)
    )

    assert response.status_code == 201
    assert len(response.json()["spools"]) == 21
    assert (await auth_client.get("/api/v1/spools/batch-limit")).json() == {"limit": 50}


@pytest.mark.asyncio
async def test_replay_survives_a_lowered_limit(
    auth_client, db_session: AsyncSession, auth_user: User
):
    filament = await _filament(db_session)
    limit_row = UserLimit(user_id=auth_user.id, spool_batch_limit=50)
    db_session.add(limit_row)
    await db_session.commit()
    body = _body(filament.id, quantity=21)
    first = await auth_client.post("/api/v1/spools/batch", json=body)
    assert first.status_code == 201
    await db_session.delete(limit_row)
    await db_session.commit()

    retry = await auth_client.post("/api/v1/spools/batch", json=body)

    assert retry.status_code == 201
    assert retry.json()["replayed"] is True
    assert len(retry.json()["spools"]) == 21
