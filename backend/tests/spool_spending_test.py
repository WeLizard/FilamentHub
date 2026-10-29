"""Personal filament spending: what was bought, what was used, what is unknown."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.spool_usage_service import record_spool_usage, revert_spool_usage
from app.services.spoolmanager_import_service import parse_purchase_date

URL = "/api/v1/spools/spending"


def _spool(user_id: int, *, price: float | None, currency: str | None = "RUB", **kw) -> UserSpool:
    return UserSpool(
        user_id=user_id,
        initial_weight_g=kw.pop("initial_weight_g", 1000.0),
        used_weight_g=kw.pop("used_weight_g", 0.0),
        price=price,
        state=kw.pop("state", UserSpoolState.shelf),
        source="manual",
        extra={"currency": currency} if currency else {},
        **kw,
    )


async def _save(db: AsyncSession, *items) -> None:
    db.add_all(items)
    await db.commit()


async def _use(db: AsyncSession, spool: UserSpool, grams: float, **kw) -> PresetUsageEvent:
    spool.used_weight_g += grams
    event = await record_spool_usage(
        db,
        spool=spool,
        event_type=kw.pop("event_type", PresetUsageEventType.manual_adjust),
        delta_weight_g=grams,
        **kw,
    )
    await db.commit()
    return event


def _row(body: dict, currency: str | None) -> dict:
    return next(r for r in body["currencies"] if r["currency"] == currency)


@pytest.mark.asyncio
async def test_consumption_counts_only_real_usage(auth_client, auth_user, db_session):
    spool = _spool(auth_user.id, price=1000.0)
    await _save(db_session, spool)
    await _use(db_session, spool, 100)
    await _use(
        db_session, spool, 500, event_type=PresetUsageEventType.reconcile_adjust,
        meta={"reason": "opening_balance"},
    )
    await _use(db_session, spool, 50, event_type=PresetUsageEventType.reconcile_adjust,
               meta={"balance_observed_at": datetime.now(timezone.utc).isoformat()})
    spool.used_weight_g -= 400
    db_session.add(
        PresetUsageEvent(
            user_id=auth_user.id, spool_id=spool.id,
            event_type=PresetUsageEventType.print_estimate, delta_weight_g=300,
        )
    )
    await record_spool_usage(
        db_session, spool=spool, event_type=PresetUsageEventType.printer_report,
        delta_weight_g=0.0, reported_weight_g=70.0,
        meta={"balance_accounting": "needs_reconciliation"},
    )
    await db_session.commit()

    body = (await auth_client.get(URL)).json()
    row = _row(body, "RUB")
    assert row["consumed_grams_priced"] == 150.0
    assert row["consumed_value"] == 150.0
    assert body["unpriced"]["unreconciled_grams"] == 70.0


@pytest.mark.asyncio
async def test_reverted_edit_nets_to_zero(auth_client, auth_user, db_session):
    spool = _spool(auth_user.id, price=1000.0)
    await _save(db_session, spool)
    event = await _use(db_session, spool, 200)
    await revert_spool_usage(db_session, user_id=auth_user.id, spool_id=spool.id, event_id=event.id)

    body = (await auth_client.get(URL)).json()
    assert _row(body, "RUB")["consumed_value"] == 0.0
    assert _row(body, "RUB")["consumed_grams_priced"] == 0.0


@pytest.mark.asyncio
async def test_deleted_spool_keeps_cost_through_snapshot(auth_client, auth_user, db_session):
    spool = _spool(auth_user.id, price=800.0, initial_weight_g=800.0)
    await _save(db_session, spool)
    event = await _use(db_session, spool, 100)
    assert event.meta["price_per_g"] == 1.0 and event.meta["currency"] == "RUB"
    await db_session.execute(delete(UserSpool).where(UserSpool.id == spool.id))
    await db_session.commit()
    db_session.expire_all()

    body = (await auth_client.get(URL)).json()
    assert _row(body, "RUB")["consumed_value"] == 100.0
    assert body["unpriced"]["consumed_grams_without_price"] == 0.0


@pytest.mark.asyncio
async def test_unknown_price_is_unpriced_and_zero_is_a_price(auth_client, auth_user, db_session):
    unknown = _spool(auth_user.id, price=None)
    free = _spool(auth_user.id, price=0.0)
    await _save(db_session, unknown, free)
    await _use(db_session, unknown, 120)
    await _use(db_session, free, 30)

    body = (await auth_client.get(URL)).json()
    assert body["unpriced"]["spools_without_price"] == 1
    assert body["unpriced"]["spools_total"] == 2
    assert body["unpriced"]["consumed_grams_without_price"] == 120.0
    row = _row(body, "RUB")
    assert row["consumed_grams_priced"] == 30.0 and row["consumed_value"] == 0.0
    assert row["bought_priced_count"] == 1 and row["bought_count"] == 2


@pytest.mark.asyncio
async def test_currencies_are_never_mixed(auth_client, auth_user, db_session):
    await _save(
        db_session,
        _spool(auth_user.id, price=1000.0, currency="RUB"),
        _spool(auth_user.id, price=20.0, currency="USD"),
        _spool(auth_user.id, price=5.0, currency=None),
    )
    body = (await auth_client.get(URL)).json()
    assert [r["currency"] for r in body["currencies"]] == ["RUB", "USD", None]
    assert _row(body, "RUB")["bought_total"] == 1000.0
    assert _row(body, "USD")["bought_total"] == 20.0
    assert _row(body, None)["bought_total"] == 5.0
    assert _row(body, "RUB")["shelf_value"] == 1000.0


@pytest.mark.asyncio
async def test_weighted_price_per_kg_and_catalog_price(auth_client, auth_user, db_session):
    brand = Brand(name="Spend Brand", slug="spend-brand", verified=True, active=True, currency="RUB")
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id, name="PLA", slug="spend-pla", material_type="PLA",
        color_name="Red", color_hex="CC0000", diameter=1.75, density=1.24,
        spool_weight=1000.0, active=True, price_per_kg=1500.0,
    )
    db_session.add(filament)
    await db_session.flush()
    await _save(
        db_session,
        _spool(auth_user.id, price=1000.0, filament_id=filament.id),
        _spool(auth_user.id, price=1000.0, initial_weight_g=500.0, filament_id=filament.id),
        _spool(auth_user.id, price=300.0, initial_weight_g=1000.0),
    )
    body = (await auth_client.get(URL)).json()
    brand_row = next(g for g in body["by_brand"] if g["key"] == "Spend Brand")
    assert brand_row["bought_total"] == 2000.0
    assert brand_row["price_per_kg"] == pytest.approx(2000 / 1500 * 1000, abs=0.01)
    assert brand_row["catalog_price_per_kg"] == 1500.0
    unlinked = next(g for g in body["by_material"] if g["key"] is None)
    assert unlinked["price_per_kg"] == 300.0 and unlinked["catalog_price_per_kg"] is None

    brand.price_hidden = True
    await db_session.commit()
    body = (await auth_client.get(URL)).json()
    assert next(g for g in body["by_brand"] if g["key"] == "Spend Brand")["catalog_price_per_kg"] is None


@pytest.mark.asyncio
async def test_purchase_date_prefers_column_over_creation(auth_client, auth_user, db_session):
    today = datetime.now(timezone.utc).date()
    old = (today.replace(day=1) - timedelta(days=62)).replace(day=10)
    await _save(
        db_session,
        _spool(auth_user.id, price=100.0, purchased_on=old),
        _spool(auth_user.id, price=40.0),
        _spool(auth_user.id, price=999.0, purchased_on=date(2001, 1, 1)),
    )
    body = (await auth_client.get(URL)).json()
    by_month = {m["month"]: m["currencies"] for m in body["by_month"]}
    assert by_month[old.strftime("%Y-%m")][0]["bought_total"] == 100.0
    assert by_month[today.strftime("%Y-%m")][0]["bought_total"] == 40.0
    assert _row(body, "RUB")["bought_total"] == 140.0
    assert len(body["by_month"]) == 12


def test_import_purchase_date_parsing():
    assert parse_purchase_date("05.03.2024") == date(2024, 3, 5)
    assert parse_purchase_date("31.02.2024") is None
    assert parse_purchase_date("") is None
    assert parse_purchase_date(None) is None


@pytest.mark.asyncio
async def test_other_users_data_is_not_counted(auth_client, auth_user, admin_user, db_session):
    await _save(db_session, _spool(admin_user.id, price=5000.0))
    body = (await auth_client.get(URL)).json()
    assert body["currencies"] == [] and body["unpriced"]["spools_total"] == 0
    assert (await auth_client.get(URL, params={"months": 25})).status_code == 422
