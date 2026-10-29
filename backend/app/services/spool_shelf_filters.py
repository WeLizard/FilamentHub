"""Filters shared by the flat spool feed and the grouped shelf."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import ColumnElement, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_SPOOL_GROUP_KEY_INVALID, raise_error
from app.models.filament import Filament
from app.models.spool_collection import SpoolCollectionMember
from app.models.user_spool import UserSpool, UserSpoolState

AVAILABLE_STATES = (UserSpoolState.active, UserSpoolState.shelf)
ARCHIVED_STATES = (UserSpoolState.archived, UserSpoolState.empty)


NO_TYPE_KEY = "t:_none"


def group_key_filter(group_key: str) -> ColumnElement[bool]:
    """Spools of one shelf group: material, manufacturer, base type, or one lone spool."""
    kind, _, raw = group_key.partition(":")
    if kind == "t" and raw and len(raw) <= 50:
        typed = select(Filament.id).where(Filament.base_material_type.is_not(None))
        if raw == "_none":
            return or_(UserSpool.filament_id.is_(None), UserSpool.filament_id.not_in(typed))
        return UserSpool.filament_id.in_(typed.where(Filament.base_material_type == raw))
    if kind not in {"f", "c", "s", "b", "n"} or not raw.isdigit() or not 0 <= int(raw) <= 2_147_483_647:
        raise_error(422, ERR_SPOOL_GROUP_KEY_INVALID)
    value = int(raw)
    if kind == "b":
        if value == 0:
            return UserSpool.filament_id.is_(None)
        return UserSpool.filament_id.in_(select(Filament.id).where(Filament.brand_id == value))
    if kind == "n":
        return UserSpool.filament_id.is_(None) & UserSpool.compat_filament_ref_id.is_(None)
    if value == 0:
        raise_error(422, ERR_SPOOL_GROUP_KEY_INVALID)
    if kind == "f":
        return UserSpool.filament_id == value
    if kind == "c":
        return (UserSpool.filament_id.is_(None)) & (UserSpool.compat_filament_ref_id == value)
    return (
        (UserSpool.id == value)
        & UserSpool.filament_id.is_(None)
        & UserSpool.compat_filament_ref_id.is_(None)
    )


def shelf_filters(
    user_id: int,
    *,
    state: UserSpoolState | None = None,
    state_group: str | None = None,
    filament_id: int | None = None,
    group_key: str | None = None,
    collection_id: int | None = None,
    no_collection: bool = False,
) -> list[ColumnElement[bool]]:
    """Membership is tested with EXISTS so a spool in many folders is still one row."""
    filters: list[ColumnElement[bool]] = [UserSpool.user_id == user_id]
    if filament_id is not None:
        filters.append(UserSpool.filament_id == filament_id)
    if group_key is not None:
        filters.append(group_key_filter(group_key))
    if state is not None:
        filters.append(UserSpool.state == state)
    elif state_group == "available":
        filters.append(UserSpool.state.in_(AVAILABLE_STATES))
    elif state_group == "archived":
        filters.append(UserSpool.state.in_(ARCHIVED_STATES))
    member = exists().where(SpoolCollectionMember.spool_id == UserSpool.id)
    if collection_id is not None:
        filters.append(member.where(SpoolCollectionMember.collection_id == collection_id))
    elif no_collection:
        filters.append(~member)
    return filters


async def collection_ids_by_spool(
    db: AsyncSession, spool_ids: Iterable[int]
) -> dict[int, list[int]]:
    ids = list(spool_ids)
    if not ids:
        return {}
    result: dict[int, list[int]] = defaultdict(list)
    rows = await db.execute(
        select(SpoolCollectionMember.spool_id, SpoolCollectionMember.collection_id)
        .where(SpoolCollectionMember.spool_id.in_(ids))
        .order_by(SpoolCollectionMember.collection_id)
    )
    for spool_id, collection_id in rows.all():
        result[spool_id].append(collection_id)
    return result
