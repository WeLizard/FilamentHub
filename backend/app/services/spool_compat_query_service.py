"""SQL filtering of account inventory in its compatibility identity space."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased, joinedload

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.spool_compat_resource_service import get_spool_material_context


def text_filter(column, raw):
    if raw is None:
        return None
    terms = [term.strip() for term in raw.split(",") if term.strip()]
    comparisons = []
    for term in terms:
        if len(term) >= 2 and term.startswith('"') and term.endswith('"'):
            comparisons.append(func.lower(column) == term[1:-1].lower())
        else:
            comparisons.append(func.lower(column).contains(term.lower(), autoescape=True))
    return or_(*comparisons) if comparisons else None


async def inventory_query(db, *, user_id):
    # New native spools acquire an explicit resource before any wire-ID filter.
    # Existing inventory is backfilled by the migration, so this is normally empty.
    missing = (await db.scalars(
        select(UserSpool).where(
            UserSpool.user_id == user_id, UserSpool.compat_filament_ref_id.is_(None)
        )
    )).all()
    for spool in missing:
        await get_spool_material_context(db, user_id=user_id, spool=spool)
    await db.flush()

    material = aliased(SpoolCompatResource)
    vendor = aliased(SpoolCompatResource)
    query = (
        select(UserSpool)
        .outerjoin(material, material.id == UserSpool.compat_filament_ref_id)
        .outerjoin(Filament, Filament.id == UserSpool.filament_id)
        .outerjoin(Brand, Brand.id == Filament.brand_id)
        .outerjoin(vendor, and_(
            vendor.kind == "vendor",
            or_(
                and_(Filament.id.is_not(None), vendor.source_kind == "catalog",
                     vendor.brand_id == Brand.id),
                and_(Filament.id.is_(None),
                     vendor.wire_id == material.latest_payload["vendor_id"].as_integer(),
                     or_(vendor.user_id.is_(None), vendor.user_id == user_id)),
            ),
        ))
        .where(UserSpool.user_id == user_id)
    )
    columns = {
        "id": UserSpool.id,
        "registered": UserSpool.created_at,
        "first_used": UserSpool.first_used_at,
        "last_used": UserSpool.last_used_at,
        "lot_nr": UserSpool.lot_nr,
        "price": UserSpool.price,
        "initial_weight": UserSpool.initial_weight_g,
        "used_weight": UserSpool.used_weight_g,
        "remaining_weight": UserSpool.initial_weight_g - UserSpool.used_weight_g,
        "filament.id": material.wire_id,
        "filament.name": func.coalesce(Filament.name, material.latest_payload["name"].as_string()),
        "filament.material": func.coalesce(
            Filament.material_type, material.latest_payload["material"].as_string()
        ),
        "filament.vendor.id": vendor.wire_id,
        "filament.vendor.name": func.coalesce(
            Brand.name, vendor.latest_payload["name"].as_string(),
            material.latest_payload["brand_name"].as_string(),
            material.latest_payload["vendor"]["name"].as_string(),
        ),
        "filament.external_id": material.external_id,
    }
    return query, columns


async def filtered_inventory(
    db, *, user_id, allow_archived, filters, id_filters,
    location_spool_ids, location_include_unassigned, assigned_spool_ids,
    tag_spool_id, sort, limit, offset,
):
    query, columns = await inventory_query(db, user_id=user_id)
    if not allow_archived:
        query = query.where(UserSpool.state.notin_([UserSpoolState.archived, UserSpoolState.empty]))
    for key, value in filters.items():
        condition = text_filter(columns[key], value)
        if condition is not None:
            query = query.where(condition)
    for key, values in id_filters.items():
        if values is not None:
            query = query.where(columns[key].in_(values))
    if location_spool_ids is not None:
        condition = UserSpool.id.in_(location_spool_ids)
        if location_include_unassigned:
            condition = or_(condition, UserSpool.id.notin_(assigned_spool_ids))
        query = query.where(condition)
    if tag_spool_id is not None:
        query = query.where(UserSpool.id == tag_spool_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    ordering = []
    if sort:
        for item in sort.split(","):
            key, _, direction = item.partition(":")
            if key not in columns or direction.lower() not in {"", "asc", "desc"}:
                raise ValueError("Invalid spool sort field or direction.")
            column = columns[key]
            ordering.append(column.desc().nulls_last() if direction.lower() == "desc" else column.asc().nulls_first())
    else:
        ordering.append(UserSpool.created_at.desc())
    query = query.order_by(*ordering, UserSpool.id).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    query = query.options(
        joinedload(UserSpool.filament).joinedload(Filament.brand),
        joinedload(UserSpool.filament).selectinload(Filament.presets),
    )
    return list((await db.scalars(query)).all()), int(total or 0)
