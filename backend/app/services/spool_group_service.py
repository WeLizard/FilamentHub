"""Grouped shelf and personal folders over a user's spools.

A group is spools of one catalog material kept as separate physical spools;
nothing is merged. Folders are the person's own labels, a spool may be in many.
Totals are computed over distinct spools (EXISTS filters, one group per spool),
never by summing folders.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timezone

from sqlalchemy import String, and_, case, cast, delete, func, literal, literal_column, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_SPOOL_COLLECTION_EXISTS,
    ERR_SPOOL_COLLECTION_LIMIT,
    ERR_SPOOL_COLLECTION_NOT_FOUND,
    ERR_SPOOL_CURSOR_INVALID,
    raise_error,
)
from app.models.filament import Filament
from app.models.spool_collection import SpoolCollection, SpoolCollectionMember
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.spool import (
    SpoolCollectionResponse,
    SpoolGroupFeedResponse,
    SpoolGroupResponse,
    SpoolGroupSummary,
    SpoolStateCounts,
)
from app.services.spool_service import _build_response
from app.services.spool_shelf_filters import (
    AVAILABLE_STATES,
    NO_TYPE_KEY,
    collection_ids_by_spool,
    shelf_filters,
)

MAX_COLLECTIONS = 100

# How the shelf is folded: one group per product (default), per manufacturer,
# or per base material type. Spools without a catalog filament share one
# "none" bucket in the last two modes.
_BRAND_KEY = case(
    (Filament.brand_id.is_not(None), "b:" + cast(Filament.brand_id, String)),
    else_="b:0",
)
_TYPE_KEY = case(
    (Filament.base_material_type.is_not(None), "t:" + Filament.base_material_type),
    else_=NO_TYPE_KEY,
)

_GROUP_KEY = case(
    (UserSpool.filament_id.is_not(None), "f:" + cast(UserSpool.filament_id, String)),
    (
        UserSpool.compat_filament_ref_id.is_not(None),
        "c:" + cast(UserSpool.compat_filament_ref_id, String),
    ),
    # Spools with no catalog card share one bucket, shown last.
    else_=literal("n:0"),
)
# Mass is unknown when the spool has no usable size; it never counts as 0 g.
_MASS_KNOWN = UserSpool.initial_weight_g > 0
_REMAINING = case(
    (
        UserSpool.initial_weight_g > UserSpool.used_weight_g,
        UserSpool.initial_weight_g - UserSpool.used_weight_g,
    ),
    else_=0,
)


def _encode_cursor(latest: datetime, latest_id: int) -> str:
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    raw = json.dumps(
        [latest.astimezone(timezone.utc).isoformat(), latest_id], separators=(",", ":")
    )
    return base64.urlsafe_b64encode(raw.encode()).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        latest = datetime.fromisoformat(payload[0])
        if latest.tzinfo is None or not isinstance(payload[1], int) or isinstance(payload[1], bool):
            raise ValueError("bad cursor")
        return latest.astimezone(timezone.utc), payload[1]
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        IndexError,
    ):
        raise_error(422, ERR_SPOOL_CURSOR_INVALID)


async def list_spool_groups(
    db: AsyncSession,
    user_id: int,
    *,
    limit: int,
    cursor: str | None = None,
    state: UserSpoolState | None = None,
    state_group: str | None = None,
    collection_id: int | None = None,
    no_collection: bool = False,
    group_by: str = "product",
) -> SpoolGroupFeedResponse:
    filters = shelf_filters(
        user_id,
        state=state,
        state_group=state_group,
        collection_id=collection_id,
        no_collection=no_collection,
    )
    available = UserSpool.state.in_(AVAILABLE_STATES)

    def counted(target: UserSpoolState):
        return func.coalesce(func.sum(case((UserSpool.state == target, 1), else_=0)), 0)

    known_remaining = func.coalesce(
        func.sum(case((and_(available, _MASS_KNOWN), _REMAINING), else_=0)), 0
    )
    unknown_mass = func.coalesce(func.sum(case((~_MASS_KNOWN, 1), else_=0)), 0)
    latest = func.max(UserSpool.created_at).label("latest")
    latest_id = func.max(UserSpool.id).label("latest_id")
    group_key = {"brand": _BRAND_KEY, "type": _TYPE_KEY}.get(group_by, _GROUP_KEY)
    none_key = {"brand": "b:0", "type": NO_TYPE_KEY}.get(group_by, "n:0")
    grouped = (
        select(
            group_key.label("key"),
            func.count(UserSpool.id).label("spool_count"),
            latest,
            latest_id,
            counted(UserSpoolState.active).label("n_active"),
            counted(UserSpoolState.shelf).label("n_shelf"),
            counted(UserSpoolState.archived).label("n_archived"),
            counted(UserSpoolState.empty).label("n_empty"),
            known_remaining.label("remaining"),
            unknown_mass.label("unknown"),
        )
        .where(*filters)
        # Grouping by the output name keeps PostgreSQL from seeing two different
        # parameterised CASE expressions in SELECT and GROUP BY.
        .group_by(literal_column("key"))
    )
    if group_by in {"brand", "type"}:
        grouped = grouped.outerjoin(Filament, Filament.id == UserSpool.filament_id)
    # The "no catalog card" bucket is not part of the keyset order; it closes the
    # final page so it is always listed last.
    paged = grouped.where(group_key != none_key)
    if cursor is not None:
        cursor_at, cursor_id = _decode_cursor(cursor)
        paged = paged.having(
            or_(latest < cursor_at, and_(latest == cursor_at, latest_id < cursor_id))
        )
    rows = (
        await db.execute(paged.order_by(latest.desc(), latest_id.desc()).limit(limit + 1))
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].latest, rows[-1].latest_id) if has_more and rows else None
    if not has_more:
        rows += (await db.execute(grouped.where(group_key == none_key))).all()

    totals = (
        await db.execute(
            select(func.count(UserSpool.id), known_remaining, unknown_mass).where(*filters)
        )
    ).one()
    group_count = await db.scalar(select(func.count()).select_from(grouped.subquery())) or 0

    spools = {
        spool.id: spool
        for spool in (
            await db.execute(
                select(UserSpool).where(UserSpool.id.in_([row.latest_id for row in rows]))
            )
        ).scalars()
    }
    filament_ids = {spool.filament_id for spool in spools.values() if spool.filament_id}
    filaments: dict[int, Filament] = {}
    if filament_ids:
        found = await db.execute(
            select(Filament)
            .options(joinedload(Filament.brand))
            .where(Filament.id.in_(filament_ids))
        )
        filaments = {item.id: item for item in found.unique().scalars()}
    folders = await collection_ids_by_spool(db, spools)

    items: list[SpoolGroupResponse] = []
    for row in rows:
        spool = spools[row.latest_id]
        representative = _build_response(spool, filaments.get(spool.filament_id))
        representative.collection_ids = folders.get(spool.id, [])
        items.append(
            SpoolGroupResponse(
                key=row.key,
                spool_count=row.spool_count,
                state_counts=SpoolStateCounts(
                    active=row.n_active,
                    shelf=row.n_shelf,
                    archived=row.n_archived,
                    empty=row.n_empty,
                ),
                available_remaining_weight_g=float(row.remaining),
                unknown_mass_count=int(row.unknown),
                latest_spool=representative,
            )
        )
    return SpoolGroupFeedResponse(
        items=items,
        next_cursor=next_cursor,
        summary=SpoolGroupSummary(
            total=int(totals[0]),
            group_count=int(group_count),
            available_remaining_weight_g=float(totals[1]),
            unknown_mass_count=int(totals[2]),
        ),
    )


async def _owned_collection(db: AsyncSession, user_id: int, collection_id: int) -> SpoolCollection:
    collection = await db.scalar(
        select(SpoolCollection).where(
            SpoolCollection.id == collection_id, SpoolCollection.user_id == user_id
        )
    )
    if collection is None:
        raise_error(404, ERR_SPOOL_COLLECTION_NOT_FOUND)
    return collection


async def list_collections(db: AsyncSession, user_id: int) -> list[SpoolCollectionResponse]:
    rows = await db.execute(
        select(SpoolCollection, func.count(SpoolCollectionMember.spool_id))
        .outerjoin(SpoolCollectionMember, SpoolCollectionMember.collection_id == SpoolCollection.id)
        .where(SpoolCollection.user_id == user_id)
        .group_by(SpoolCollection.id)
        .order_by(SpoolCollection.name_key)
    )
    return [
        SpoolCollectionResponse(id=collection.id, name=collection.name, spool_count=count)
        for collection, count in rows.all()
    ]


async def create_collection(db: AsyncSession, user_id: int, name: str) -> SpoolCollectionResponse:
    existing = await db.scalar(
        select(func.count()).select_from(SpoolCollection).where(SpoolCollection.user_id == user_id)
    )
    if (existing or 0) >= MAX_COLLECTIONS:
        raise_error(409, ERR_SPOOL_COLLECTION_LIMIT, {"limit": MAX_COLLECTIONS})
    collection = SpoolCollection(user_id=user_id, name=name, name_key=name.casefold())
    db.add(collection)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise_error(409, ERR_SPOOL_COLLECTION_EXISTS)
    return SpoolCollectionResponse(id=collection.id, name=collection.name, spool_count=0)


async def rename_collection(
    db: AsyncSession, user_id: int, collection_id: int, name: str
) -> SpoolCollectionResponse:
    collection = await _owned_collection(db, user_id, collection_id)
    collection.name, collection.name_key = name, name.casefold()
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise_error(409, ERR_SPOOL_COLLECTION_EXISTS)
    count = await db.scalar(
        select(func.count()).where(SpoolCollectionMember.collection_id == collection_id)
    )
    return SpoolCollectionResponse(id=collection_id, name=name, spool_count=count or 0)


async def delete_collection(db: AsyncSession, user_id: int, collection_id: int) -> None:
    """Remove the folder and its links only; spools, history and rules stay."""
    collection = await _owned_collection(db, user_id, collection_id)
    await db.execute(
        delete(SpoolCollectionMember).where(SpoolCollectionMember.collection_id == collection_id)
    )
    await db.delete(collection)
    await db.commit()


async def update_members(
    db: AsyncSession, user_id: int, collection_id: int, add: list[int], remove: list[int]
) -> SpoolCollectionResponse:
    """Idempotent add/remove; a request naming anyone else's spool fails as a whole."""
    collection = await _owned_collection(db, user_id, collection_id)
    wanted = set(add) | set(remove)
    if wanted:
        owned = set(
            (
                await db.execute(
                    select(UserSpool.id).where(
                        UserSpool.user_id == user_id, UserSpool.id.in_(wanted)
                    )
                )
            ).scalars()
        )
        if owned != wanted:
            raise_error(404, ERR_ACCESS_DENIED)
        present = set(
            (
                await db.execute(
                    select(SpoolCollectionMember.spool_id).where(
                        SpoolCollectionMember.collection_id == collection_id,
                        SpoolCollectionMember.spool_id.in_(wanted),
                    )
                )
            ).scalars()
        )
        for spool_id in set(add) - set(remove) - present:
            db.add(SpoolCollectionMember(collection_id=collection_id, spool_id=spool_id))
        for member in (
            await db.execute(
                select(SpoolCollectionMember).where(
                    SpoolCollectionMember.collection_id == collection_id,
                    SpoolCollectionMember.spool_id.in_(set(remove) - set(add)),
                )
            )
        ).scalars():
            await db.delete(member)
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent identical add already linked it: the end state is the same.
        await db.rollback()
    count = await db.scalar(
        select(func.count()).where(SpoolCollectionMember.collection_id == collection.id)
    )
    return SpoolCollectionResponse(id=collection.id, name=collection.name, spool_count=count or 0)
