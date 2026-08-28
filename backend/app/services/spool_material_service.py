"""Canonical material-identity guard for existing physical spools."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_MANUFACTURER_QR_MATERIAL_LOCKED,
    ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE,
    raise_error,
)
from app.models.qr_identity import (
    QrManufacturerInstanceState,
    QrManufacturerInstanceStatus,
    QrUserSpoolBinding,
)
from app.models.user_spool import UserSpool


async def set_spool_filament_with_qr_guard(
    db: AsyncSession,
    *,
    spool: UserSpool,
    filament_id: int | None,
) -> UserSpool:
    """Lock a spool and reject identity-breaking ordinary material changes."""
    locked = cast(
        UserSpool | None,
        await db.scalar(
            select(UserSpool)
            .where(UserSpool.id == spool.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ),
    )
    if locked is None:  # pragma: no cover - caller owns an already-loaded row
        raise RuntimeError("spool disappeared before material update")
    if locked.filament_id == filament_id:
        return locked

    manufacturer_claim = await db.scalar(
        select(QrManufacturerInstanceState.id).where(
            QrManufacturerInstanceState.user_spool_id == locked.id,
            QrManufacturerInstanceState.status == QrManufacturerInstanceStatus.CLAIMED,
        )
    )
    if manufacturer_claim is not None:
        raise_error(409, ERR_MANUFACTURER_QR_MATERIAL_LOCKED)

    user_binding = await db.scalar(
        select(QrUserSpoolBinding.id).where(QrUserSpoolBinding.user_spool_id == locked.id)
    )
    if user_binding is not None:
        raise_error(409, ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE)

    locked.filament_id = filament_id
    return locked
