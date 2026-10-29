"""What a person spent on filament and what of it has been used.

Everything is summed in the database per currency; rates are never converted.
Consumption is priced from the rate stored on each ledger row, so a deleted
spool or a later price edit does not change what the grams cost.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool_spending import (
    SpendingCurrency,
    SpendingGroup,
    SpendingMonth,
    SpendingMonthCurrency,
    SpendingUnpriced,
    SpoolSpendingResponse,
)
from app.services.month_buckets import (
    date_month_index_expr,
    last_month_indexes,
    month_index_expr,
    month_label,
    month_start,
)

GROUP_LIMIT = 20
_BALANCE_ACCOUNTED = ("already_in_balance", "prorated_after_balance", "reconciled_by_measurement")


def _money(value: float | Decimal | None) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), ROUND_HALF_UP))


def _grams(value: float | None) -> float:
    return round(float(value or 0.0), 1)


def _currency_order(code: str | None) -> tuple[int, str]:
    return (1, "") if code is None else (0, code)


def _spool_currency():
    return func.nullif(UserSpool.extra["currency"].as_string(), "")


def _has_rate():
    return and_(UserSpool.price.is_not(None), UserSpool.initial_weight_g > 0)


def _remaining():
    return case(
        (
            UserSpool.initial_weight_g > UserSpool.used_weight_g,
            UserSpool.initial_weight_g - UserSpool.used_weight_g,
        ),
        else_=0.0,
    )


def _purchase_month(dialect_name: str):
    return case(
        (UserSpool.purchased_on.is_not(None), date_month_index_expr(UserSpool.purchased_on)),
        else_=month_index_expr(UserSpool.created_at, dialect_name),
    )


def _counted_grams():
    """The grams one ledger row adds to consumption, as spool_usage_service counts them."""
    meta = PresetUsageEvent.meta
    delta = func.coalesce(PresetUsageEvent.delta_weight_g, 0.0)
    return case(
        (meta["reverted"].as_boolean().is_(True), delta),
        (meta["consumption_kind"].as_string() == "estimated", 0.0),
        (
            meta["balance_accounting"].as_string().in_(_BALANCE_ACCOUNTED),
            func.coalesce(meta["reported_weight_g"].as_float(), 0.0),
        ),
        else_=delta,
    )


def _event_filters(user_id: int, start: datetime):
    meta = PresetUsageEvent.meta
    reverted = meta["reverted"].as_boolean().is_(True)
    return (
        PresetUsageEvent.user_id == user_id,
        PresetUsageEvent.created_at >= start,
        PresetUsageEvent.event_type != PresetUsageEventType.print_estimate,
        or_(
            PresetUsageEvent.event_type != PresetUsageEventType.reconcile_adjust,
            func.coalesce(meta["reason"].as_string(), "") != "opening_balance",
        ),
        or_(
            func.coalesce(meta["balance_accounting"].as_string(), "") != "needs_reconciliation",
            reverted,
        ),
    )


async def _bought(db: AsyncSession, user_id: int, window: list[int], dialect: str):
    currency = _spool_currency().label("currency")
    month = _purchase_month(dialect).label("month")
    rows = await db.execute(
        select(
            currency,
            month,
            func.count(UserSpool.id),
            func.count(UserSpool.price),
            func.coalesce(func.sum(UserSpool.price), 0.0),
        )
        .where(
            UserSpool.user_id == user_id,
            _purchase_month(dialect).between(window[0], window[-1]),
        )
        .group_by(currency, month)
    )
    return [
        (code, int(index), int(count), int(priced), total)
        for code, index, count, priced, total in rows
    ]


async def _consumed(db: AsyncSession, user_id: int, window: list[int], dialect: str):
    meta = PresetUsageEvent.meta
    snapshot_rate = meta["price_per_g"].as_float()
    spool_rate = case((_has_rate(), UserSpool.price / UserSpool.initial_weight_g))
    rate = func.coalesce(snapshot_rate, spool_rate)
    grams = _counted_grams()
    currency = case(
        (snapshot_rate.is_not(None), func.nullif(meta["currency"].as_string(), "")),
        else_=_spool_currency(),
    ).label("currency")
    month = month_index_expr(PresetUsageEvent.created_at, dialect).label("month")
    rows = await db.execute(
        select(
            currency,
            month,
            func.coalesce(func.sum(case((rate.is_not(None), grams * rate), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((rate.is_not(None), grams), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((rate.is_(None), grams), else_=0.0)), 0.0),
        )
        .select_from(PresetUsageEvent)
        .outerjoin(UserSpool, UserSpool.id == PresetUsageEvent.spool_id)
        .where(*_event_filters(user_id, month_start(window[0])))
        .group_by(currency, month)
    )
    return [
        (code, int(index), Decimal(str(value)), float(priced), float(unpriced))
        for code, index, value, priced, unpriced in rows
    ]


async def _shelf(db: AsyncSession, user_id: int):
    currency = _spool_currency().label("currency")
    remaining = _remaining()
    rows = await db.execute(
        select(
            currency,
            func.coalesce(
                func.sum(
                    case(
                        (_has_rate(), remaining * UserSpool.price / UserSpool.initial_weight_g),
                        else_=0.0,
                    )
                ),
                0.0,
            ),
            func.coalesce(func.sum(case((_has_rate(), remaining), else_=0.0)), 0.0),
            func.coalesce(func.sum(case((UserSpool.price.is_(None), remaining), else_=0.0)), 0.0),
        )
        .where(
            UserSpool.user_id == user_id,
            UserSpool.state.in_((UserSpoolState.active, UserSpoolState.shelf)),
        )
        .group_by(currency)
    )
    return list(rows)


async def _group_rows(
    db: AsyncSession, user_id: int, window: list[int], dialect: str, key_column
) -> list[SpendingGroup]:
    currency = _spool_currency().label("currency")
    key = key_column.label("key")
    catalog_rate = and_(
        Filament.price_per_kg.is_not(None),
        Brand.price_hidden.is_(False),
        Brand.currency == _spool_currency(),
    )
    grouped = (
        select(
            currency,
            key,
            func.sum(UserSpool.price).label("bought_total"),
            func.count(UserSpool.id).label("bought_count"),
            func.sum(UserSpool.initial_weight_g).label("initial_weight_g"),
            func.sum(
                case((catalog_rate, Filament.price_per_kg * UserSpool.initial_weight_g))
            ).label("catalog_numerator"),
            func.sum(case((catalog_rate, UserSpool.initial_weight_g))).label("catalog_weight"),
        )
        .select_from(UserSpool)
        .outerjoin(Filament, Filament.id == UserSpool.filament_id)
        .outerjoin(Brand, Brand.id == Filament.brand_id)
        .where(
            UserSpool.user_id == user_id,
            _has_rate(),
            _purchase_month(dialect).between(window[0], window[-1]),
        )
        .group_by(currency, key)
        .subquery()
    )
    ranked = select(
        grouped,
        func.row_number()
        .over(partition_by=grouped.c.currency, order_by=grouped.c.bought_total.desc())
        .label("rank"),
    ).subquery()
    rows = await db.execute(select(ranked).where(ranked.c.rank <= GROUP_LIMIT))
    groups: list[SpendingGroup] = []
    for row in rows:
        initial = Decimal(str(row.initial_weight_g or 0))
        total = Decimal(str(row.bought_total or 0))
        catalog_weight = Decimal(str(row.catalog_weight or 0))
        groups.append(
            SpendingGroup(
                key=row.key,
                currency=row.currency,
                bought_total=_money(total),
                bought_count=int(row.bought_count),
                initial_weight_g=_grams(float(initial)),
                price_per_kg=_money(total / initial * 1000) if initial > 0 else None,
                catalog_price_per_kg=(
                    _money(Decimal(str(row.catalog_numerator)) / catalog_weight)
                    if catalog_weight > 0
                    else None
                ),
            )
        )
    groups.sort(key=lambda g: (_currency_order(g.currency), -g.bought_total))
    return groups


async def spool_spending(db: AsyncSession, user_id: int, months: int) -> SpoolSpendingResponse:
    dialect = db.get_bind().dialect.name
    window = last_month_indexes(datetime.now(timezone.utc), months)

    bought = await _bought(db, user_id, window, dialect)
    consumed = await _consumed(db, user_id, window, dialect)
    shelf = await _shelf(db, user_id)

    totals = await db.execute(
        select(func.count(UserSpool.id), func.count(UserSpool.price)).where(
            UserSpool.user_id == user_id
        )
    )
    spools_total, spools_priced = totals.one()

    unreconciled = await db.scalar(
        select(func.coalesce(func.sum(PresetUsageEvent.meta["reported_weight_g"].as_float()), 0.0))
        .where(
            PresetUsageEvent.user_id == user_id,
            PresetUsageEvent.created_at >= month_start(window[0]),
            PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
            PresetUsageEvent.meta["balance_accounting"].as_string() == "needs_reconciliation",
            PresetUsageEvent.meta["reverted"].as_boolean().is_not(True),
        )
    )

    per_currency: dict[str | None, dict] = defaultdict(
        lambda: {
            "bought_total": Decimal(0),
            "bought_count": 0,
            "bought_priced_count": 0,
            "consumed_value": Decimal(0),
            "consumed_grams_priced": 0.0,
            "shelf_value": Decimal(0),
            "shelf_grams": 0.0,
        }
    )
    per_month: dict[int, dict[str | None, list[Decimal]]] = {
        index: defaultdict(lambda: [Decimal(0), Decimal(0)]) for index in window
    }
    for code, index, count, priced, total in bought:
        row = per_currency[code]
        row["bought_total"] += Decimal(str(total))
        row["bought_count"] += count
        row["bought_priced_count"] += priced
        per_month[index][code][0] += Decimal(str(total))
    grams_without_price = 0.0
    for code, index, value, priced_grams, unpriced_grams in consumed:
        grams_without_price += unpriced_grams
        if index not in per_month or (priced_grams == 0 and value == 0):
            continue
        row = per_currency[code]
        row["consumed_value"] += value
        row["consumed_grams_priced"] += priced_grams
        per_month[index][code][1] += value
    shelf_grams_without_price = 0.0
    for code, value, grams, grams_unpriced in shelf:
        shelf_grams_without_price += float(grams_unpriced or 0.0)
        if not grams and not value:
            continue
        row = per_currency[code]
        row["shelf_value"] += Decimal(str(value or 0))
        row["shelf_grams"] += float(grams or 0.0)

    return SpoolSpendingResponse(
        months=months,
        currencies=[
            SpendingCurrency(
                currency=code,
                bought_total=_money(row["bought_total"]),
                bought_count=row["bought_count"],
                bought_priced_count=row["bought_priced_count"],
                consumed_value=_money(row["consumed_value"]),
                consumed_grams_priced=_grams(row["consumed_grams_priced"]),
                shelf_value=_money(row["shelf_value"]),
                shelf_grams=_grams(row["shelf_grams"]),
            )
            for code, row in sorted(per_currency.items(), key=lambda item: _currency_order(item[0]))
        ],
        unpriced=SpendingUnpriced(
            spools_without_price=int(spools_total) - int(spools_priced),
            spools_total=int(spools_total),
            consumed_grams_without_price=_grams(grams_without_price),
            unreconciled_grams=_grams(unreconciled),
            shelf_grams_without_price=_grams(shelf_grams_without_price),
        ),
        by_month=[
            SpendingMonth(
                month=month_label(index),
                currencies=[
                    SpendingMonthCurrency(
                        currency=code,
                        bought_total=_money(bought_value),
                        consumed_value=_money(value),
                    )
                    for code, (bought_value, value) in sorted(
                        per_month[index].items(), key=lambda item: _currency_order(item[0])
                    )
                ],
            )
            for index in window
        ],
        by_brand=await _group_rows(db, user_id, window, dialect, Brand.name),
        by_material=await _group_rows(
            db,
            user_id,
            window,
            dialect,
            func.coalesce(Filament.base_material_type, Filament.material_type),
        ),
    )
