"""Business logic for user spool (filament inventory) management."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_FILAMENT_NOT_FOUND,
    ERR_SPOOL_EMPTY_ON_CREATE,
    ERR_SPOOL_USED_EXCEEDS_INITIAL,
    raise_error,
)
from app.models.filament import Filament
from app.models.preset_gate_state import PresetGateState, PresetGateStateSource
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import (
    SpoolCreateRequest,
    SpoolFilamentInfo,
    SpoolResponse,
    SpoolUpdateRequest,
)


def clear_spool_location_projection(spool: UserSpool) -> None:
    extra = dict(spool.extra or {})
    extra["printer_name"] = json.dumps("")
    extra["mmu_gate_map"] = json.dumps(-1)
    spool.extra = extra


async def clear_spool_gate_assignments(
    db: AsyncSession,
    spool: UserSpool,
    *,
    source: PresetGateStateSource = PresetGateStateSource.web_manual,
    except_device_id: int | None = None,
    except_gate_index: int | None = None,
) -> int:
    """Clear canonical gate bindings for a physical spool without committing."""
    result = await db.execute(
        select(PresetGateState)
        .where(PresetGateState.spool_id == spool.id)
        .with_for_update()
    )
    states = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    cleared = 0
    for gate_state in states:
        if (
            except_device_id is not None
            and except_gate_index is not None
            and gate_state.device_id == except_device_id
            and gate_state.gate_index == except_gate_index
        ):
            continue
        gate_state.spool_id = None
        gate_state.source = source
        gate_state.source_ts = now
        gate_state.is_active = True
        cleared += 1

    if cleared:
        clear_spool_location_projection(spool)
    return cleared


async def spool_has_gate_assignment(db: AsyncSession, spool_id: int) -> bool:
    result = await db.execute(
        select(PresetGateState.id)
        .where(PresetGateState.spool_id == spool_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _validate_spool_weights(initial_weight_g: float, used_weight_g: float) -> None:
    if used_weight_g > initial_weight_g:
        raise_error(400, ERR_SPOOL_USED_EXCEEDS_INITIAL)


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
    _validate_spool_weights(payload.initial_weight_g, payload.used_weight_g)
    if (
        payload.used_weight_g >= payload.initial_weight_g
        or payload.state == UserSpoolState.empty.value
    ):
        raise_error(400, ERR_SPOOL_EMPTY_ON_CREATE)

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

    next_initial_weight = (
        payload.initial_weight_g
        if payload.initial_weight_g is not None
        else spool.initial_weight_g
    )
    next_used_weight = (
        payload.used_weight_g
        if payload.used_weight_g is not None
        else spool.used_weight_g
    )
    _validate_spool_weights(next_initial_weight, next_used_weight)
    spool.initial_weight_g = next_initial_weight
    spool.used_weight_g = next_used_weight
    if payload.state is not None:
        spool.state = UserSpoolState(payload.state)
    if "price" in payload.model_fields_set:
        spool.price = payload.price
    if "lot_nr" in payload.model_fields_set:
        spool.lot_nr = payload.lot_nr
    if "comment" in payload.model_fields_set:
        spool.comment = payload.comment

    if spool.state == UserSpoolState.empty:
        spool.used_weight_g = spool.initial_weight_g
    elif spool.remaining_weight_g <= 0:
        spool.state = UserSpoolState.empty

    if spool.state in {
        UserSpoolState.shelf,
        UserSpoolState.archived,
        UserSpoolState.empty,
    }:
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

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
    if spool.first_used_at is None:
        spool.first_used_at = spool.last_used_at

    if spool.remaining_weight_g <= 0:
        spool.state = UserSpoolState.empty
        await clear_spool_gate_assignments(db, spool)
        clear_spool_location_projection(spool)

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
