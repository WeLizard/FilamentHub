"""Low-stock alerts for single spools and for a material's stock on the shelf.

An alert fires once when stock falls below its threshold and is re-armed only
after a refill or replacement lifts it clear of the threshold (twice the
threshold), so readings that wobble around the line do not repeat it. Alerts are
recomputed by the services that change stock, inside the same transaction; a
page view never triggers one. A spool of unknown size is never treated as empty.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.errors import ERR_ACCESS_DENIED, raise_error
from app.models.filament import Filament
from app.models.notification import Notification, NotificationType
from app.models.stock_alert_rule import StockAlertRule
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.spool_shelf_filters import AVAILABLE_STATES, group_key_filter

DEFAULT_THRESHOLD_G = 100.0
REARM_FACTOR = 2.0
SPOOLS_LINK = "/profile?tab=spools"

TITLE_SPOOL = "low_stock_spool"
TITLE_MATERIAL = "low_stock_material"


def material_key(spool: UserSpool) -> str | None:
    if spool.filament_id is not None:
        return f"f:{spool.filament_id}"
    if spool.compat_filament_ref_id is not None:
        return f"c:{spool.compat_filament_ref_id}"
    return None


def _mass_known(spool: UserSpool) -> bool:
    return spool.initial_weight_g > 0


async def _display_name(db: AsyncSession, spool: UserSpool) -> str:
    if spool.filament_id is not None:
        filament = await db.scalar(
            select(Filament)
            .options(joinedload(Filament.brand))
            .where(Filament.id == spool.filament_id)
        )
        if filament is not None:
            brand = filament.brand.name if filament.brand is not None else None
            return f"{brand} {filament.name}" if brand else filament.name
    extra = spool.extra or {}
    return str(extra.get("display_name") or f"#{spool.id}")


async def refresh_stock_alerts(
    db: AsyncSession, spool: UserSpool, *, announce: bool = True
) -> None:
    """Recompute this spool's alert and its material's shelf alert after stock changed."""
    if spool.id is None:
        await db.flush()
    key = material_key(spool)
    rules = (
        (
            await db.execute(
                select(StockAlertRule).where(
                    StockAlertRule.user_id == spool.user_id,
                    StockAlertRule.enabled.is_(True),
                    (StockAlertRule.scope == "all")
                    | (StockAlertRule.spool_id == spool.id)
                    | ((StockAlertRule.scope == "material") & (StockAlertRule.material_key == key)),
                )
            )
        )
        .scalars()
        .all()
    )
    by_scope = {"spool": None, "all": None, "material": None}
    for rule in rules:
        by_scope[rule.scope] = rule
    await _evaluate_spool(db, spool, by_scope["spool"] or by_scope["all"], announce)
    if key is not None:
        await _evaluate_material(db, spool, key, by_scope["material"], announce)


async def _evaluate_spool(
    db: AsyncSession, spool: UserSpool, rule: StockAlertRule | None, announce: bool
) -> None:
    if rule is None:
        if spool.low_stock_fired:
            await db.execute(
                update(UserSpool).where(UserSpool.id == spool.id).values(low_stock_fired=False)
            )
            set_committed_value(spool, "low_stock_fired", False)
        return
    if not _mass_known(spool) or spool.state not in AVAILABLE_STATES:
        return
    remaining = spool.remaining_weight_g
    if remaining < rule.threshold_g:
        # Compare-and-set: of several concurrent readings exactly one wins.
        won = await db.execute(
            update(UserSpool)
            .where(UserSpool.id == spool.id, UserSpool.low_stock_fired.is_(False))
            .values(low_stock_fired=True)
        )
        if won.rowcount == 1:
            set_committed_value(spool, "low_stock_fired", True)
        if won.rowcount == 1 and announce:
            db.add(
                Notification(
                    user_id=spool.user_id,
                    type=NotificationType.LOW_STOCK_SPOOL,
                    title=TITLE_SPOOL,
                    message=TITLE_SPOOL + "_message",
                    link=SPOOLS_LINK,
                    extra_data={
                        "spool_id": spool.id,
                        "name": await _display_name(db, spool),
                        "remaining_g": round(remaining),
                        "threshold_g": round(rule.threshold_g),
                    },
                    read=False,
                )
            )
    elif remaining >= rule.threshold_g * REARM_FACTOR and spool.low_stock_fired:
        await db.execute(
            update(UserSpool)
            .where(UserSpool.id == spool.id, UserSpool.low_stock_fired.is_(True))
            .values(low_stock_fired=False)
        )
        set_committed_value(spool, "low_stock_fired", False)


@dataclass
class ShelfStock:
    grams: float
    unknown_count: int


async def shelf_stock(db: AsyncSession, user_id: int, key: str) -> ShelfStock:
    """Known grams of a material on the shelf; spools of unknown size only raise a flag."""
    known = UserSpool.initial_weight_g > 0
    remaining = case(
        (
            UserSpool.initial_weight_g > UserSpool.used_weight_g,
            UserSpool.initial_weight_g - UserSpool.used_weight_g,
        ),
        else_=0,
    )
    row = (
        await db.execute(
            select(
                func.coalesce(func.sum(case((known, remaining), else_=0)), 0),
                func.coalesce(func.sum(case((known, 0), else_=1)), 0),
            ).where(
                UserSpool.user_id == user_id,
                UserSpool.state == UserSpoolState.shelf,
                group_key_filter(key),
            )
        )
    ).one()
    return ShelfStock(grams=float(row[0]), unknown_count=int(row[1]))


async def _evaluate_material(
    db: AsyncSession, spool: UserSpool, key: str, rule: StockAlertRule | None, announce: bool
) -> None:
    if rule is None:
        return
    stock = await shelf_stock(db, spool.user_id, key)
    if stock.grams < rule.threshold_g:
        won = await db.execute(
            update(StockAlertRule)
            .where(StockAlertRule.id == rule.id, StockAlertRule.fired.is_(False))
            .values(fired=True)
        )
        if won.rowcount == 1 and announce:
            db.add(
                Notification(
                    user_id=spool.user_id,
                    type=NotificationType.LOW_STOCK_MATERIAL,
                    title=TITLE_MATERIAL,
                    message=TITLE_MATERIAL + "_message",
                    link=SPOOLS_LINK,
                    extra_data={
                        "material_key": key,
                        "name": await _display_name(db, spool),
                        "shelf_g": round(stock.grams),
                        "threshold_g": round(rule.threshold_g),
                        "unknown_count": stock.unknown_count,
                    },
                    read=False,
                )
            )
    elif stock.grams >= rule.threshold_g * REARM_FACTOR and rule.fired:
        await db.execute(
            update(StockAlertRule)
            .where(StockAlertRule.id == rule.id, StockAlertRule.fired.is_(True))
            .values(fired=False)
        )


# ---------------------------------------------------------------- rule management


async def list_rules(db: AsyncSession, user_id: int) -> list[StockAlertRule]:
    result = await db.scalars(
        select(StockAlertRule).where(StockAlertRule.user_id == user_id).order_by(StockAlertRule.id)
    )
    return list(result)


async def _silently_arm_spools(
    db: AsyncSession, user_id: int, threshold: float, spool_filter
) -> None:
    """A new or changed rule is not a crossing: spools already below start as 'fired'."""
    below = and_(
        UserSpool.initial_weight_g > 0,
        UserSpool.state.in_(AVAILABLE_STATES),
        (UserSpool.initial_weight_g - UserSpool.used_weight_g) < threshold,
    )
    await db.execute(
        update(UserSpool)
        .where(UserSpool.user_id == user_id, spool_filter)
        .values(low_stock_fired=case((below, True), else_=False))
    )


async def upsert_rule(
    db: AsyncSession,
    user_id: int,
    *,
    scope: str,
    spool_id: int | None,
    material_key_value: str | None,
    threshold_g: float,
    enabled: bool,
) -> StockAlertRule:
    query = select(StockAlertRule).where(
        StockAlertRule.user_id == user_id, StockAlertRule.scope == scope
    )
    if scope == "spool":
        owned = await db.scalar(
            select(UserSpool.id).where(UserSpool.id == spool_id, UserSpool.user_id == user_id)
        )
        if owned is None:
            raise_error(404, ERR_ACCESS_DENIED)
        query = query.where(StockAlertRule.spool_id == spool_id)
    elif scope == "material":
        owned = await db.scalar(
            select(UserSpool.id)
            .where(UserSpool.user_id == user_id, group_key_filter(material_key_value or ""))
            .limit(1)
        )
        if owned is None:
            raise_error(404, ERR_ACCESS_DENIED)
        query = query.where(StockAlertRule.material_key == material_key_value)
    rule = await db.scalar(query.with_for_update())
    if rule is None:
        rule = StockAlertRule(
            user_id=user_id,
            scope=scope,
            spool_id=spool_id if scope == "spool" else None,
            material_key=material_key_value if scope == "material" else None,
            threshold_g=threshold_g,
            enabled=enabled,
        )
        db.add(rule)
    else:
        rule.threshold_g, rule.enabled = threshold_g, enabled
    await db.flush()
    await _rearm_for_rule(db, rule)
    await db.commit()
    return rule


async def _rearm_for_rule(db: AsyncSession, rule: StockAlertRule) -> None:
    if rule.scope == "material":
        stock = await shelf_stock(db, rule.user_id, rule.material_key or "")
        rule.fired = stock.grams < rule.threshold_g
        return
    if not rule.enabled:
        # No rule speaks for these spools now (a wider one may; it re-arms on the next reading).
        flag_off = (
            UserSpool.id == rule.spool_id if rule.scope == "spool" else UserSpool.id.is_not(None)
        )
        await db.execute(
            update(UserSpool)
            .where(UserSpool.user_id == rule.user_id, flag_off)
            .values(low_stock_fired=False)
        )
        return
    if rule.scope == "spool":
        await _silently_arm_spools(
            db, rule.user_id, rule.threshold_g, UserSpool.id == rule.spool_id
        )
    else:
        own = select(StockAlertRule.spool_id).where(
            StockAlertRule.user_id == rule.user_id,
            StockAlertRule.scope == "spool",
            StockAlertRule.enabled.is_(True),
        )
        await _silently_arm_spools(db, rule.user_id, rule.threshold_g, UserSpool.id.not_in(own))


async def delete_rule(db: AsyncSession, user_id: int, rule_id: int) -> None:
    rule = await db.scalar(
        select(StockAlertRule).where(
            StockAlertRule.id == rule_id, StockAlertRule.user_id == user_id
        )
    )
    if rule is None:
        raise_error(404, ERR_ACCESS_DENIED)
    rule.enabled = False
    await _rearm_for_rule(db, rule)
    await db.delete(rule)
    await db.commit()


async def list_alert_events(
    db: AsyncSession, user_id: int, *, after_id: int, limit: int
) -> tuple[list[Notification], int]:
    """Alert notifications newer than a cursor, for the desktop plugin to show once each."""
    kinds = (NotificationType.LOW_STOCK_SPOOL, NotificationType.LOW_STOCK_MATERIAL)
    latest = await db.scalar(
        select(func.max(Notification.id)).where(
            Notification.user_id == user_id, Notification.type.in_(kinds)
        )
    )
    rows = (
        await db.scalars(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.type.in_(kinds),
                Notification.id > after_id,
            )
            .order_by(Notification.id)
            .limit(limit)
        )
    ).all()
    return list(rows), int(latest or 0)
