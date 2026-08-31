"""Canonical tag-to-spool binding operations."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tag_identity import normalize_tag_format, normalize_tag_uid
from app.models.spool_tag import SpoolTag
from app.models.user_spool import UserSpool


class SpoolTagConflict(Exception):
    def __init__(self, uid: str, spool_id: int) -> None:
        super().__init__(f"Tag {uid} is already linked to spool {spool_id}.")
        self.uid = uid
        self.spool_id = spool_id


async def list_spool_tags(
    db: AsyncSession,
    *,
    user_id: int,
    spool_ids: Iterable[int] | None = None,
) -> dict[int, list[SpoolTag]]:
    query = select(SpoolTag).where(SpoolTag.user_id == user_id)
    if spool_ids is not None:
        ids = set(spool_ids)
        if not ids:
            return {}
        query = query.where(SpoolTag.spool_id.in_(ids))
    rows = list(
        (
            await db.scalars(
                query.order_by(SpoolTag.spool_id, SpoolTag.created_at, SpoolTag.id)
            )
        ).all()
    )
    result: dict[int, list[SpoolTag]] = {}
    for row in rows:
        result.setdefault(row.spool_id, []).append(row)
    return result


async def find_spool_tag(
    db: AsyncSession,
    *,
    user_id: int,
    uid: str,
) -> SpoolTag | None:
    normalized = normalize_tag_uid(uid)
    return await db.scalar(
        select(SpoolTag).where(
            SpoolTag.user_id == user_id,
            SpoolTag.uid == normalized,
        )
    )


async def _require_owned_spool(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
) -> UserSpool | None:
    return await db.scalar(
        select(UserSpool)
        .where(UserSpool.id == spool_id, UserSpool.user_id == user_id)
        .with_for_update()
    )


async def link_spool_tag(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
    uid: str,
    technology: str = "unknown",
    tag_format: str | None = None,
    source: str,
) -> SpoolTag | None:
    """Link idempotently; return None when the owned spool does not exist."""
    normalized = normalize_tag_uid(uid)
    normalized_format = normalize_tag_format(tag_format)
    spool = await _require_owned_spool(db, user_id=user_id, spool_id=spool_id)
    if spool is None:
        return None

    existing = await db.scalar(
        select(SpoolTag)
        .where(SpoolTag.user_id == user_id, SpoolTag.uid == normalized)
        .with_for_update()
    )
    if existing is not None:
        if existing.spool_id != spool_id:
            raise SpoolTagConflict(normalized, existing.spool_id)
        if normalized_format is not None:
            existing.format = normalized_format
        if technology != "unknown" or existing.technology == "unknown":
            existing.technology = technology
        existing.source = source
        return existing

    tag = SpoolTag(
        user_id=user_id,
        spool_id=spool_id,
        uid=normalized,
        technology=technology,
        format=normalized_format,
        source=source,
    )
    try:
        async with db.begin_nested():
            db.add(tag)
            await db.flush()
    except IntegrityError:
        winner = await db.scalar(
            select(SpoolTag).where(
                SpoolTag.user_id == user_id,
                SpoolTag.uid == normalized,
            )
        )
        if winner is None:
            raise
        if winner.spool_id != spool_id:
            raise SpoolTagConflict(normalized, winner.spool_id) from None
        return winner
    return tag


async def replace_spool_tags(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
    uids: list[str],
    technology: str,
    source: str,
) -> list[SpoolTag] | None:
    """Atomically replace one spool's tag set after checking all conflicts."""
    spool = await _require_owned_spool(db, user_id=user_id, spool_id=spool_id)
    if spool is None:
        return None
    normalized = list(dict.fromkeys(normalize_tag_uid(uid) for uid in uids))
    conflicts = list(
        (
            await db.scalars(
                select(SpoolTag)
                .where(
                    SpoolTag.user_id == user_id,
                    SpoolTag.uid.in_(normalized),
                    SpoolTag.spool_id != spool_id,
                )
                .with_for_update()
            )
        ).all()
    ) if normalized else []
    if conflicts:
        raise SpoolTagConflict(conflicts[0].uid, conflicts[0].spool_id)

    stale_tags = delete(SpoolTag).where(
        SpoolTag.user_id == user_id,
        SpoolTag.spool_id == spool_id,
    )
    if normalized:
        stale_tags = stale_tags.where(SpoolTag.uid.not_in(normalized))
    await db.execute(stale_tags)
    for uid in normalized:
        await link_spool_tag(
            db,
            user_id=user_id,
            spool_id=spool_id,
            uid=uid,
            technology=technology,
            source=source,
        )
    return (await list_spool_tags(db, user_id=user_id, spool_ids=[spool_id])).get(spool_id, [])


async def unlink_spool_tag(
    db: AsyncSession,
    *,
    user_id: int,
    spool_id: int,
    uid: str,
) -> bool:
    normalized = normalize_tag_uid(uid)
    result = await db.execute(
        delete(SpoolTag).where(
            SpoolTag.user_id == user_id,
            SpoolTag.spool_id == spool_id,
            SpoolTag.uid == normalized,
        )
    )
    return bool(result.rowcount)
