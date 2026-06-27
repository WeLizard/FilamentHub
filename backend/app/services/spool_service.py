"""Business logic for user spool (filament inventory) management."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import ERR_ACCESS_DENIED, ERR_FILAMENT_NOT_FOUND, raise_error
from app.models.filament import Filament
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import (
    SpoolCreateRequest,
    SpoolFilamentInfo,
    SpoolResponse,
    SpoolUpdateRequest,
)


async def _load_filament_info(db: AsyncSession, filament_id: int) -> Filament | None:
    result = await db.execute(
        select(Filament)
        .options(joinedload(Filament.brand))
        .where(Filament.id == filament_id)
    )
    return result.unique().scalars().first()


def _build_response(spool: UserSpool, filament: Filament | None) -> SpoolResponse:
    fil_info: SpoolFilamentInfo | None = None
    if filament is not None:
        fil_info = SpoolFilamentInfo(
            id=filament.id,
            name=filament.name,
            material_type=filament.material_type,
            color_name=filament.color_name,
            color_hex=filament.color_hex,
            brand_name=filament.brand.name if filament.brand is not None else None,
            price_per_kg=filament.price_per_kg,
            currency=filament.brand.currency if filament.brand is not None else None,
        )
    return SpoolResponse(
        id=spool.id,
        user_id=spool.user_id,
        filament_id=spool.filament_id,
        filament=fil_info,
        initial_weight_g=spool.initial_weight_g,
        used_weight_g=spool.used_weight_g,
        remaining_weight_g=spool.remaining_weight_g,
        remaining_pct=spool.remaining_pct,
        price=spool.price,
        state=spool.state.value,
        source=spool.source,
        lot_nr=spool.lot_nr,
        comment=spool.comment,
        created_at=spool.created_at,
        updated_at=spool.updated_at,
        last_used_at=spool.last_used_at,
        extra=spool.extra,
    )


async def list_spools(db: AsyncSession, user_id: int) -> list[SpoolResponse]:
    result = await db.execute(
        select(UserSpool)
        .where(UserSpool.user_id == user_id)
        .order_by(UserSpool.created_at.desc())
    )
    spools = list(result.scalars().all())

    # Batch load filaments
    fil_ids = {s.filament_id for s in spools if s.filament_id}
    filaments: dict[int, Filament] = {}
    if fil_ids:
        fil_result = await db.execute(
            select(Filament)
            .options(joinedload(Filament.brand))
            .where(Filament.id.in_(fil_ids))
        )
        filaments = {f.id: f for f in fil_result.unique().scalars().all()}

    return [_build_response(s, filaments.get(s.filament_id) if s.filament_id else None) for s in spools]


async def create_spool(
    db: AsyncSession,
    user: User,
    payload: SpoolCreateRequest,
) -> SpoolResponse:
    if payload.filament_id is not None:
        filament = await _load_filament_info(db, payload.filament_id)
        if filament is None:
            raise_error(404, ERR_FILAMENT_NOT_FOUND)
    else:
        filament = None

    spool = UserSpool(
        user_id=user.id,
        filament_id=payload.filament_id,
        initial_weight_g=payload.initial_weight_g,
        used_weight_g=payload.used_weight_g,
        price=payload.price,
        state=UserSpoolState(payload.state),
        source=payload.source,
        lot_nr=payload.lot_nr,
        comment=payload.comment,
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def update_spool(
    db: AsyncSession,
    user: User,
    spool_id: int,
    payload: SpoolUpdateRequest,
) -> SpoolResponse:
    result = await db.execute(
        select(UserSpool).where(UserSpool.id == spool_id)
    )
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)

    if "filament_id" in payload.model_fields_set:
        if payload.filament_id is not None:
            filament = await _load_filament_info(db, payload.filament_id)
            if filament is None:
                raise_error(404, ERR_FILAMENT_NOT_FOUND)
        else:
            filament = None
        spool.filament_id = payload.filament_id
    else:
        filament = await _load_filament_info(db, spool.filament_id) if spool.filament_id else None

    if payload.initial_weight_g is not None:
        spool.initial_weight_g = payload.initial_weight_g
    if payload.used_weight_g is not None:
        spool.used_weight_g = payload.used_weight_g
    if payload.state is not None:
        spool.state = UserSpoolState(payload.state)
    if "price" in payload.model_fields_set:
        spool.price = payload.price
    if "lot_nr" in payload.model_fields_set:
        spool.lot_nr = payload.lot_nr
    if "comment" in payload.model_fields_set:
        spool.comment = payload.comment

    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def use_spool(
    db: AsyncSession,
    user: User,
    spool_id: int,
    delta_weight_g: float,
) -> SpoolResponse:
    result = await db.execute(
        select(UserSpool).where(UserSpool.id == spool_id)
    )
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)

    spool.used_weight_g = min(
        spool.initial_weight_g,
        spool.used_weight_g + delta_weight_g,
    )
    spool.last_used_at = datetime.now(timezone.utc)

    if spool.remaining_weight_g <= 0:
        spool.state = UserSpoolState.empty

    filament = await _load_filament_info(db, spool.filament_id) if spool.filament_id else None
    await db.commit()
    await db.refresh(spool)
    return _build_response(spool, filament)


async def delete_spool(db: AsyncSession, user: User, spool_id: int) -> None:
    result = await db.execute(
        select(UserSpool).where(UserSpool.id == spool_id)
    )
    spool = result.scalars().first()
    if spool is None or spool.user_id != user.id:
        raise_error(404, ERR_ACCESS_DENIED)
    await db.delete(spool)
    await db.commit()
