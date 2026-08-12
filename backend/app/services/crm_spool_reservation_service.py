"""Explicit order reservations layered over the shared UserSpool inventory."""

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_CRM_ORDER_HAS_NO_MATERIAL_PLAN,
    ERR_CRM_ORDER_RESERVATION_NOT_EDITABLE,
    ERR_CRM_SPOOL_RESERVATION_EXCEEDS_AVAILABLE,
    ERR_CRM_SPOOL_RESERVATION_MATERIAL_MISMATCH,
    ERR_SPOOL_NOT_ACCESSIBLE,
    raise_error,
)
from app.models.crm import (
    CrmOrder,
    CrmOrderSpoolReservation,
    CrmOrderStatus,
    CrmReservationStatus,
)
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.crm import CrmOrderSpoolReservationReplace

_EDITABLE_ORDER_STATUSES = {CrmOrderStatus.NEW, CrmOrderStatus.PLANNED}


async def active_reserved_weights(
    db: AsyncSession,
    *,
    user_id: int,
    spool_ids: set[int],
) -> dict[int, float]:
    """Return active planned weight by physical spool."""
    if not spool_ids:
        return {}
    rows = await db.execute(
        select(
            CrmOrderSpoolReservation.spool_id,
            func.sum(CrmOrderSpoolReservation.weight_g),
        )
        .where(
            CrmOrderSpoolReservation.user_id == user_id,
            CrmOrderSpoolReservation.status == CrmReservationStatus.ACTIVE,
            CrmOrderSpoolReservation.spool_id.in_(spool_ids),
        )
        .group_by(CrmOrderSpoolReservation.spool_id)
    )
    return {spool_id: float(weight or 0) for spool_id, weight in rows}


async def release_order_reservations(
    db: AsyncSession,
    *,
    order_id: int,
    reason: str,
) -> None:
    """Release active planning holds without mutating confirmed consumption."""
    rows = await db.scalars(
        select(CrmOrderSpoolReservation)
        .where(
            CrmOrderSpoolReservation.order_id == order_id,
            CrmOrderSpoolReservation.status == CrmReservationStatus.ACTIVE,
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    for reservation in rows:
        reservation.status = CrmReservationStatus.RELEASED
        reservation.released_at = now
        reservation.release_reason = reason


async def replace_order_reservations(
    db: AsyncSession,
    *,
    order: CrmOrder,
    payload: CrmOrderSpoolReservationReplace,
) -> None:
    """Atomically replace one order's active holds after capacity and identity checks."""
    if order.status not in _EDITABLE_ORDER_STATUSES:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_CRM_ORDER_RESERVATION_NOT_EDITABLE,
            {"order_status": order.status.value},
        )

    requested_spool_ids = {item.spool_id for item in payload.items}
    spools: dict[int, UserSpool] = {}
    if requested_spool_ids:
        rows = await db.scalars(
            select(UserSpool)
            .where(
                UserSpool.user_id == order.user_id,
                UserSpool.id.in_(requested_spool_ids),
            )
            .order_by(UserSpool.id)
            .with_for_update()
        )
        spools = {spool.id: spool for spool in rows}
        missing = requested_spool_ids - set(spools)
        if missing:
            raise_error(
                status.HTTP_404_NOT_FOUND,
                ERR_SPOOL_NOT_ACCESSIBLE,
                {"spool_id": min(missing)},
            )

    requirements = {
        item.get("line_id"): item
        for item in order.material_requirements or []
        if isinstance(item, dict) and isinstance(item.get("line_id"), str)
    }
    if payload.items and not requirements:
        raise_error(status.HTTP_409_CONFLICT, ERR_CRM_ORDER_HAS_NO_MATERIAL_PLAN)
    requested_by_spool: dict[int, float] = defaultdict(float)
    for item in payload.items:
        spool = spools[item.spool_id]
        requirement = requirements.get(item.material_line_key)
        if requirement is None:
            raise_error(
                status.HTTP_409_CONFLICT,
                ERR_CRM_SPOOL_RESERVATION_MATERIAL_MISMATCH,
                {
                    "spool_id": spool.id,
                    "material_line_key": item.material_line_key,
                },
            )
        expected_filament_id = requirement.get("filament_id") if requirement else None
        if expected_filament_id is not None and spool.filament_id != expected_filament_id:
            raise_error(
                status.HTTP_409_CONFLICT,
                ERR_CRM_SPOOL_RESERVATION_MATERIAL_MISMATCH,
                {
                    "spool_id": spool.id,
                    "material_line_key": item.material_line_key,
                },
            )
        if spool.state not in {UserSpoolState.active, UserSpoolState.shelf}:
            raise_error(
                status.HTTP_409_CONFLICT,
                ERR_CRM_SPOOL_RESERVATION_EXCEEDS_AVAILABLE,
                {"spool_id": spool.id, "available_g": 0},
            )
        requested_by_spool[spool.id] += item.weight_g

    other_active: dict[int, float] = defaultdict(float)
    if requested_spool_ids:
        rows = await db.scalars(
            select(CrmOrderSpoolReservation)
            .where(
                CrmOrderSpoolReservation.user_id == order.user_id,
                CrmOrderSpoolReservation.order_id != order.id,
                CrmOrderSpoolReservation.status == CrmReservationStatus.ACTIVE,
                CrmOrderSpoolReservation.spool_id.in_(requested_spool_ids),
            )
            .with_for_update()
        )
        for reservation in rows:
            other_active[reservation.spool_id] += reservation.weight_g

    for spool_id, requested_weight in requested_by_spool.items():
        spool = spools[spool_id]
        available = max(0.0, spool.remaining_weight_g - other_active[spool_id])
        if requested_weight > available + 0.001:
            raise_error(
                status.HTTP_409_CONFLICT,
                ERR_CRM_SPOOL_RESERVATION_EXCEEDS_AVAILABLE,
                {
                    "spool_id": spool_id,
                    "requested_g": round(requested_weight, 3),
                    "available_g": round(available, 3),
                },
            )

    await release_order_reservations(db, order_id=order.id, reason="replaced")
    for item in payload.items:
        db.add(
            CrmOrderSpoolReservation(
                order_id=order.id,
                user_id=order.user_id,
                spool_id=item.spool_id,
                material_line_key=item.material_line_key,
                material_label=item.material_label,
                weight_g=item.weight_g,
            )
        )
