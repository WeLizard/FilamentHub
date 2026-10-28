"""Queue of probable duplicate filaments awaiting an administrator."""

from __future__ import annotations

import itertools
import logging

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_duplicate_review import FilamentDuplicateReview
from app.services.catalog_duplicates import same_filament_kind
from app.services.filament_identity import identity_of, probable_duplicate

logger = logging.getLogger(__name__)

PENDING = "pending"
DISMISSED = "dismissed"


def _is_probable_pair(
    left: Filament, right: Filament, left_identity, right_identity
) -> bool:
    return same_filament_kind(
        left.material_type, left.diameter, right.material_type, right.diameter
    ) and probable_duplicate(left_identity, right_identity)


async def _insert_pair(db: AsyncSession, newer_id: int, older_id: int, origin: str) -> int:
    """Insert a pending pair unless any review of it exists; safe under concurrency."""
    try:
        async with db.begin_nested():
            db.add(
                FilamentDuplicateReview(filament_id=newer_id, candidate_id=older_id, origin=origin)
            )
            await db.flush()
    except IntegrityError:
        return 0
    return 1


async def record_creation_candidates(db: AsyncSession, filament: Filament, brand: Brand) -> int:
    """Queue probable duplicates of a freshly flushed filament.

    Runs in a savepoint: a failure here must never fail the creation itself.
    """
    try:
        async with db.begin_nested():
            others = (
                await db.scalars(
                    select(Filament).where(
                        Filament.brand_id == filament.brand_id,
                        Filament.diameter == filament.diameter,
                        Filament.active.is_(True),
                        Filament.id != filament.id,
                    )
                )
            ).all()
            own_identity = identity_of(filament, brand.name)
            added = 0
            for other in others:
                if not _is_probable_pair(
                    filament, other, own_identity, identity_of(other, brand.name)
                ):
                    continue
                newer, older = (filament, other) if filament.id > other.id else (other, filament)
                added += await _insert_pair(db, newer.id, older.id, "creation")
            return added
    except Exception:
        logger.warning("Could not record duplicate candidates for filament", exc_info=True)
        # Rolling back the savepoint expires every loaded instance; reload the
        # new filament so the response can still be serialized.
        await db.refresh(filament)
        await db.refresh(brand)
        return 0


async def scan_for_duplicates(db: AsyncSession) -> int:
    """Queue every probable pair in the active catalog that has no review yet."""
    existing = {
        (filament_id, candidate_id)
        for filament_id, candidate_id in await db.execute(
            select(FilamentDuplicateReview.filament_id, FilamentDuplicateReview.candidate_id)
        )
    }
    rows = await db.execute(
        select(Filament, Brand.name)
        .join(Brand, Brand.id == Filament.brand_id)
        .where(Filament.active.is_(True))
        .order_by(Filament.brand_id, Filament.diameter, Filament.id)
    )
    groups: dict[tuple[int, float, str], list[tuple[Filament, object]]] = {}
    for filament, brand_name in rows:
        key = (filament.brand_id, filament.diameter, filament.material_type.strip().casefold())
        groups.setdefault(key, []).append(
            (filament, identity_of(filament, brand_name))
        )
    added = 0
    for group in groups.values():
        for (older, older_identity), (newer, newer_identity) in itertools.combinations(group, 2):
            if (newer.id, older.id) in existing:
                continue
            if not _is_probable_pair(older, newer, older_identity, newer_identity):
                continue
            added += await _insert_pair(db, newer.id, older.id, "scan")
    return added


async def delete_reviews_for_filament(db: AsyncSession, filament_id: int) -> None:
    """Remove review rows of a filament that is about to disappear.

    Done explicitly because the database cascade is not enforced everywhere.
    """
    await db.execute(
        delete(FilamentDuplicateReview).where(
            or_(
                FilamentDuplicateReview.filament_id == filament_id,
                FilamentDuplicateReview.candidate_id == filament_id,
            )
        )
    )
