"""Fold a duplicate brand or filament into the record that stays.

Every row that points at the duplicate is re-pointed at the kept record. Old
public addresses stay reachable through the existing slug redirects; no
separate merge log is kept.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from fastapi import status
from sqlalchemy import String, and_, cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.errors import (
    ERR_BRAND_MERGE_ANALYTICS_CONFLICT,
    ERR_BRAND_MERGE_FILAMENT_CONFLICT,
    ERR_BRAND_MERGE_PAIR_INVALID,
    ERR_BRAND_MERGE_SOURCE_REPRESENTED,
    ERR_CATALOG_MERGE_COUNTRY_CONFLICT,
    ERR_CATALOG_MERGE_SAME_RECORD,
    ERR_FILAMENT_MERGE_INCOMPATIBLE,
    ERR_FILAMENT_MERGE_QR_BATCH_CONFLICT,
    raise_error,
)
from app.models.brand import Brand
from app.models.brand_country_cell import BrandCountryCell
from app.models.brand_invite import BrandInvite
from app.models.brand_monthly_analytics_release import BrandMonthlyAnalyticsRelease
from app.models.brand_request import BrandRequest
from app.models.brand_slug_redirect import BrandSlugRedirect
from app.models.brand_territorial_grant import BrandTerritorialGrant
from app.models.crm import CrmOrder
from app.models.email_communication import EmailThread
from app.models.filament import Filament
from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.filament_country_cell import CountryAvailability, FilamentCountryCell
from app.models.filament_line import FilamentLine
from app.models.filament_qr_alias import FilamentQrAlias
from app.models.filament_review import FilamentReview
from app.models.filament_slug_redirect import FilamentSlugRedirect
from app.models.material_mapping import MaterialMapping
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.organization import OrganizationBrandAccess
from app.models.organization_label_preset import OrganizationLabelPreset
from app.models.preset import Preset
from app.models.preset_gate_state import PresetGateState
from app.models.preset_printer import PresetPrinter
from app.models.preset_usage_event import PresetUsageEvent
from app.models.preset_version import PresetVersion
from app.models.print_profile_filament import PrintProfileFilament
from app.models.qr_identity import (
    QrManufacturerBatch,
    QrManufacturerBatchItem,
    QrManufacturerInstanceState,
    QrUserSpoolBinding,
)
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.weighted_preset_refresh_job import WeightedPresetRefreshJob
from app.schemas.catalog_merge import (
    BrandDuplicatePair,
    BrandMergeFilamentRow,
    BrandMergePreview,
    FilamentMergeCandidate,
    MergeBrandSummary,
    MergeFilamentSummary,
)
from app.services.catalog_duplicates import (
    BrandIdentity,
    comparable_name,
    find_duplicate_brand_pairs,
    same_filament_color,
    same_filament_kind,
)
from app.services.catalog_url_service import choose_filament_slug
from app.services.qr_service import backfill_brand_qr_codes
from app.services.weighted_preset_reconciliation import enqueue_weighted_preset_refreshes

logger = logging.getLogger(__name__)

MERGE_CANDIDATE_LIMIT = 100

# Every foreign key into these tables must be handled below. The guard test
# compares these sets with the ORM metadata, so a new reference cannot be
# silently left pointing at a deleted duplicate.
FILAMENT_REFERENCES = frozenset(
    {
        "filament_analytics_events.filament_id",
        "filament_country_cells.filament_id",
        "filament_qr_aliases.filament_id",
        "filament_reviews.filament_id",
        "filament_slug_redirects.filament_id",
        "presets.filament_id",
        "print_profile_filaments.filament_id",
        "qr_manufacturer_batch_items.filament_id",
        "qr_manufacturer_instance_states.filament_id",
        "qr_user_spool_bindings.filament_id",
        "user_spools.filament_id",
        "weighted_preset_refresh_jobs.filament_id",
    }
)
WEIGHTED_PRESET_REFERENCES = frozenset(
    {
        "filament_reviews.preset_id",
        "material_slot_assignments.preset_id",
        "preset_gate_states.preset_id",
        "preset_printers.preset_id",
        "preset_usage_events.preset_id",
        "preset_versions.preset_id",
        "presets.derived_from_preset_id",
        "user_saved_presets.preset_id",
    }
)
BRAND_REFERENCES = frozenset(
    {
        "brand_country_cells.brand_id",
        "brand_invites.brand_id",
        "brand_monthly_analytics_releases.brand_id",
        "brand_requests.brand_id",
        "brand_slug_redirects.brand_id",
        "brand_territorial_grants.brand_id",
        "email_threads.brand_id",
        "filament_lines.brand_id",
        "filament_slug_redirects.brand_id",
        "filaments.brand_id",
        "material_mappings.brand_id",
        "organization_brand_access.brand_id",
        "organization_label_presets.brand_id",
        "qr_manufacturer_batches.brand_id",
        "users.brand_id",
    }
)


@dataclass
class FilamentContributions:
    presets: int = 0
    spools: int = 0
    reviews: int = 0


async def count_filament_contributions(
    db: AsyncSession, filament_ids: list[int]
) -> dict[int, FilamentContributions]:
    """Community work attached to each filament, counted in three queries."""
    counts = {filament_id: FilamentContributions() for filament_id in filament_ids}
    if not filament_ids:
        return counts
    presets = await db.execute(
        select(Preset.filament_id, func.count())
        .where(Preset.filament_id.in_(filament_ids), Preset.is_weighted.is_(False))
        .group_by(Preset.filament_id)
    )
    for filament_id, total in presets:
        counts[filament_id].presets = total
    spools = await db.execute(
        select(UserSpool.filament_id, func.count())
        .where(UserSpool.filament_id.in_(filament_ids))
        .group_by(UserSpool.filament_id)
    )
    for filament_id, total in spools:
        counts[filament_id].spools = total
    reviews = await db.execute(
        select(FilamentReview.filament_id, func.count())
        .where(FilamentReview.filament_id.in_(filament_ids), FilamentReview.active.is_(True))
        .group_by(FilamentReview.filament_id)
    )
    for filament_id, total in reviews:
        counts[filament_id].reviews = total
    return counts


def is_likely_same_filament(source: Filament, target: Filament) -> bool:
    return (
        same_filament_kind(source.material_type, source.diameter, target.material_type, target.diameter)
        and comparable_name(source.name) == comparable_name(target.name)
        and same_filament_color(
            target.color_name, target.color_hex, source.color_name, source.color_hex
        )
    )


def ensure_filaments_mergeable(source: Filament, target: Filament) -> None:
    if source.id == target.id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_CATALOG_MERGE_SAME_RECORD)
    if not same_filament_kind(
        source.material_type, source.diameter, target.material_type, target.diameter
    ):
        raise_error(status.HTTP_409_CONFLICT, ERR_FILAMENT_MERGE_INCOMPATIBLE)


async def _slug_taken(
    db: AsyncSession, *, brand_id: int, slug: str, planned: set[str] | None = None
) -> bool:
    if planned and slug in planned:
        return True
    current = await db.scalar(
        select(Filament.id).where(Filament.brand_id == brand_id, Filament.slug == slug)
    )
    if current is not None:
        return True
    alias = await db.scalar(
        select(FilamentSlugRedirect.id).where(
            FilamentSlugRedirect.brand_id == brand_id,
            FilamentSlugRedirect.old_slug == slug,
        )
    )
    return alias is not None


async def _drop_colliding_redirects(
    db: AsyncSession, *, filament_id: int, from_brand_id: int, to_brand_id: int
) -> None:
    """Old addresses already used in the destination brand keep their owner there."""
    if from_brand_id == to_brand_id:
        return
    taken = select(FilamentSlugRedirect.old_slug).where(
        FilamentSlugRedirect.brand_id == to_brand_id
    ).union(select(Filament.slug).where(Filament.brand_id == to_brand_id))
    await db.execute(
        delete(FilamentSlugRedirect).where(
            FilamentSlugRedirect.filament_id == filament_id,
            FilamentSlugRedirect.brand_id == from_brand_id,
            FilamentSlugRedirect.old_slug.in_(taken),
        )
    )


async def _fold_weighted_preset(db: AsyncSession, *, source_id: int, target_id: int) -> None:
    """Replace one generated projection with the other everywhere it is used.

    A filament holds at most one weighted preset, so the duplicate's projection
    cannot move with the ordinary presets when the kept filament has its own.
    """
    already_saved = select(UserSavedPreset.user_id).where(UserSavedPreset.preset_id == target_id)
    await db.execute(
        delete(UserSavedPreset).where(
            UserSavedPreset.preset_id == source_id,
            UserSavedPreset.user_id.in_(already_saved),
        )
    )
    await db.execute(
        update(UserSavedPreset)
        .where(UserSavedPreset.preset_id == source_id)
        .values(preset_id=target_id, selected_version_id=None, seen_version_id=None)
    )
    # The generated source preset is removed below. Its reviews remain on the
    # merged material as filament-level reviews instead of being attributed to
    # a different generated preset.
    await db.execute(
        update(FilamentReview)
        .where(FilamentReview.preset_id == source_id)
        .values(preset_id=None)
    )
    for model in (MaterialSlotAssignment, PresetGateState, PresetUsageEvent):
        await db.execute(
            update(model).where(model.preset_id == source_id).values(preset_id=target_id)
        )
    await db.execute(delete(PresetPrinter).where(PresetPrinter.preset_id == source_id))
    await db.execute(
        update(Preset)
        .where(Preset.derived_from_preset_id == source_id)
        .values(derived_from_preset_id=target_id)
    )
    source_versions = select(PresetVersion.id).where(PresetVersion.preset_id == source_id)
    await db.execute(
        update(Preset)
        .where(Preset.derived_from_version_id.in_(source_versions))
        .values(derived_from_version_id=None)
    )
    await db.execute(
        update(PresetVersion)
        .where(PresetVersion.preset_id == source_id)
        .values(parent_version_id=None, restored_from_version_id=None)
    )
    await db.execute(delete(PresetVersion).where(PresetVersion.preset_id == source_id))
    await db.execute(delete(Preset).where(Preset.id == source_id))


async def _preserve_colliding_reviews(db: AsyncSession, *, source_id: int, target_id: int) -> None:
    """Keep both reviews when a legacy cross-material preset link would collide."""
    source_review = aliased(FilamentReview)
    target_review = aliased(FilamentReview)
    colliding_source_ids = (
        select(source_review.id)
        .join(
            target_review,
            and_(
                target_review.filament_id == target_id,
                target_review.user_id == source_review.user_id,
                target_review.preset_id == source_review.preset_id,
            ),
        )
        .where(
            source_review.filament_id == source_id,
            source_review.user_id.is_not(None),
            source_review.preset_id.is_not(None),
        )
    )
    await db.execute(
        update(FilamentReview)
        .where(FilamentReview.id.in_(colliding_source_ids))
        .values(preset_id=None)
    )


async def _repoint_crm_requirements(db: AsyncSession, *, source_id: int, target_id: int) -> None:
    """Orders compare reserved spools with the filament they were planned for."""
    candidates = (
        await db.scalars(
            select(CrmOrder).where(
                cast(CrmOrder.material_requirements, String).like(f"%{source_id}%")
            )
        )
    ).all()
    for order in candidates:
        changed = False
        requirements = []
        for requirement in order.material_requirements or []:
            if isinstance(requirement, dict) and requirement.get("filament_id") == source_id:
                requirement = {**requirement, "filament_id": target_id}
                changed = True
            requirements.append(requirement)
        if changed:
            order.material_requirements = requirements


async def _merge_country_cells(
    db: AsyncSession,
    *,
    model: type[FilamentCountryCell] | type[BrandCountryCell],
    owner_key: str,
    source_id: int,
    target_id: int,
    fields: tuple[str, ...],
) -> None:
    """Coalesce complementary market data; refuse contradictory values."""
    source_cells = (
        await db.scalars(select(model).where(getattr(model, owner_key) == source_id))
    ).all()
    target_cells = {
        cell.country: cell
        for cell in (await db.scalars(select(model).where(getattr(model, owner_key) == target_id))).all()
    }
    for source_cell in source_cells:
        target_cell = target_cells.get(source_cell.country)
        if target_cell is None:
            setattr(source_cell, owner_key, target_id)
            continue
        if isinstance(source_cell, FilamentCountryCell):
            source_availability = source_cell.availability
            target_availability = target_cell.availability
            if source_availability != CountryAvailability.unknown:
                if (
                    target_availability != CountryAvailability.unknown
                    and target_availability != source_availability
                ):
                    raise_error(
                        status.HTTP_409_CONFLICT,
                        ERR_CATALOG_MERGE_COUNTRY_CONFLICT,
                        {"country": source_cell.country, "field": "availability"},
                    )
                target_cell.availability = source_availability
        for name in fields:
            source_value = getattr(source_cell, name)
            target_value = getattr(target_cell, name)
            if source_value is None:
                continue
            if target_value is not None and target_value != source_value:
                raise_error(
                    status.HTTP_409_CONFLICT,
                    ERR_CATALOG_MERGE_COUNTRY_CONFLICT,
                    {"country": source_cell.country, "field": name},
                )
            if target_value is None:
                setattr(target_cell, name, source_value)
        if isinstance(source_cell, FilamentCountryCell) and target_cell.price is not None:
            if target_cell.price_updated_at is None:
                target_cell.price_updated_at = source_cell.price_updated_at
                target_cell.price_updated_by_id = source_cell.price_updated_by_id
        target_cell.published = target_cell.published or source_cell.published
        await db.delete(source_cell)
    await db.flush()


async def merge_filaments(
    db: AsyncSession,
    *,
    source: Filament,
    target: Filament,
) -> None:
    """Move everything from ``source`` to ``target`` and delete ``source``.

    Presets stay separate records: they only change the filament they belong
    to. The caller owns the transaction and the permission check.
    """
    ensure_filaments_mergeable(source, target)

    shared_batch = await db.scalar(
        select(QrManufacturerBatchItem.batch_id)
        .where(
            QrManufacturerBatchItem.filament_id == source.id,
            QrManufacturerBatchItem.batch_id.in_(
                select(QrManufacturerBatchItem.batch_id).where(
                    QrManufacturerBatchItem.filament_id == target.id
                )
            ),
        )
        .limit(1)
    )
    if shared_batch is not None:
        raise_error(status.HTTP_409_CONFLICT, ERR_FILAMENT_MERGE_QR_BATCH_CONFLICT)

    weighted_rows = await db.execute(
        select(Preset.filament_id, Preset.id).where(
            Preset.filament_id.in_([source.id, target.id]),
            Preset.is_weighted.is_(True),
        )
    )
    weighted: dict[int, int] = dict(tuple(row) for row in weighted_rows)
    if source.id in weighted and target.id in weighted:
        await _fold_weighted_preset(
            db, source_id=weighted[source.id], target_id=weighted[target.id]
        )

    await _preserve_colliding_reviews(db, source_id=source.id, target_id=target.id)

    for model in (
        Preset,
        FilamentReview,
        UserSpool,
        QrUserSpoolBinding,
        QrManufacturerInstanceState,
        QrManufacturerBatchItem,
        FilamentAnalyticsEvent,
    ):
        await db.execute(
            update(model).where(model.filament_id == source.id).values(filament_id=target.id)
        )

    await _merge_country_cells(
        db,
        model=FilamentCountryCell,
        owner_key="filament_id",
        source_id=source.id,
        target_id=target.id,
        fields=(
            "price", "currency", "price_display_unit", "product_url", "purchase_links",
            "market_note", "market_color_name",
        ),
    )

    linked_profiles = select(PrintProfileFilament.print_profile_id).where(
        PrintProfileFilament.filament_id == target.id
    )
    await db.execute(
        delete(PrintProfileFilament).where(
            PrintProfileFilament.filament_id == source.id,
            PrintProfileFilament.print_profile_id.in_(linked_profiles),
        )
    )
    await db.execute(
        update(PrintProfileFilament)
        .where(PrintProfileFilament.filament_id == source.id)
        .values(filament_id=target.id, filament_slug=target.slug)
    )

    await _drop_colliding_redirects(
        db, filament_id=source.id, from_brand_id=source.brand_id, to_brand_id=target.brand_id
    )
    await db.execute(
        update(FilamentSlugRedirect)
        .where(FilamentSlugRedirect.filament_id == source.id)
        .values(filament_id=target.id, brand_id=target.brand_id)
    )

    await _repoint_crm_requirements(db, source_id=source.id, target_id=target.id)

    await db.execute(
        delete(WeightedPresetRefreshJob).where(WeightedPresetRefreshJob.filament_id == source.id)
    )
    await enqueue_weighted_preset_refreshes(db, [target.id])

    await db.execute(
        update(FilamentQrAlias)
        .where(FilamentQrAlias.filament_id == source.id)
        .values(filament_id=target.id)
    )

    target.views_count = (target.views_count or 0) + (source.views_count or 0)
    target.scans_count = (target.scans_count or 0) + (source.scans_count or 0)
    # The kept record retains its canonical code. A different printed source
    # code remains a permanent alias, including for old instance envelopes.
    source_qr_code = source.qr_code
    transferred_qr_code = source_qr_code if not target.qr_code else None
    source.qr_code = None
    await db.flush()

    if source_qr_code and not transferred_qr_code:
        db.add(FilamentQrAlias(code=source_qr_code, filament_id=target.id))

    source_slug = source.slug
    await db.execute(delete(Filament).where(Filament.id == source.id))
    db.expunge(source)
    if transferred_qr_code:
        target.qr_code = transferred_qr_code

    if not await _slug_taken(db, brand_id=target.brand_id, slug=source_slug):
        db.add(
            FilamentSlugRedirect(
                filament_id=target.id,
                brand_id=target.brand_id,
                old_slug=source_slug,
                reason="merge",
            )
        )
    await db.flush()


async def lock_filaments(db: AsyncSession, *ids: int) -> dict[int, Filament]:
    rows = (
        await db.scalars(
            select(Filament).where(Filament.id.in_(ids)).order_by(Filament.id).with_for_update()
        )
    ).all()
    return {row.id: row for row in rows}


async def lock_brands(db: AsyncSession, *ids: int) -> dict[int, Brand]:
    rows = (
        await db.scalars(
            select(Brand).where(Brand.id.in_(ids)).order_by(Brand.id).with_for_update()
        )
    ).all()
    return {row.id: row for row in rows}


async def brand_is_represented(db: AsyncSession, brand: Brand) -> bool:
    """A brand that belongs to a manufacturer must not disappear by merge."""
    if brand.verified or brand.organization_id is not None:
        return True
    for model in (
        BrandTerritorialGrant,
        OrganizationBrandAccess,
        OrganizationLabelPreset,
        QrManufacturerBatch,
    ):
        if await db.scalar(select(model.id).where(model.brand_id == brand.id).limit(1)):
            return True
    return False


@dataclass
class FilamentMovePlan:
    filament: Filament
    new_slug: str
    merge_into: Filament | None = None


@dataclass
class BrandMergePlan:
    source: Brand
    target: Brand
    moves: list[FilamentMovePlan] = field(default_factory=list)
    conflicts: list[Filament] = field(default_factory=list)


async def plan_brand_merge(
    db: AsyncSession,
    *,
    source: Brand,
    target: Brand,
    pairs: dict[int, int],
) -> BrandMergePlan:
    """Decide where each filament of ``source`` ends up, without writing."""
    if source.id == target.id:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_CATALOG_MERGE_SAME_RECORD)
    source_filaments = (
        await db.scalars(
            select(Filament).where(Filament.brand_id == source.id).order_by(Filament.id)
        )
    ).all()
    by_id = {filament.id: filament for filament in source_filaments}
    target_filaments = {
        filament.id: filament
        for filament in (
            await db.scalars(select(Filament).where(Filament.brand_id == target.id))
        ).all()
    }
    for source_id, target_id in pairs.items():
        if source_id not in by_id or target_id not in target_filaments:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_MERGE_PAIR_INVALID)
        ensure_filaments_mergeable(by_id[source_id], target_filaments[target_id])

    plan = BrandMergePlan(source=source, target=target)
    planned: set[str] = set()
    for filament in source_filaments:
        if filament.id in pairs:
            plan.moves.append(
                FilamentMovePlan(
                    filament, filament.slug, merge_into=target_filaments[pairs[filament.id]]
                )
            )
            continue
        slug = filament.slug
        if await _slug_taken(db, brand_id=target.id, slug=filament.slug, planned=planned):
            holder = next(
                (item for item in target_filaments.values() if item.slug == filament.slug),
                None,
            )
            # The address encodes name and colour: the same address on the same
            # kind of material is the same product, and only a person may
            # decide to keep both.
            if holder is not None and same_filament_kind(
                filament.material_type, filament.diameter, holder.material_type, holder.diameter
            ):
                plan.conflicts.append(filament)
                continue
            alternative = await choose_filament_slug(
                db,
                brand_id=target.id,
                name=filament.name,
                color_name=filament.color_name,
                ral_code=filament.ral_code,
                diameter=filament.diameter,
            )
            if alternative is None or alternative in planned:
                plan.conflicts.append(filament)
                continue
            slug = alternative
        planned.add(slug)
        plan.moves.append(FilamentMovePlan(filament, slug))
    return plan


async def merge_brands(db: AsyncSession, plan: BrandMergePlan) -> None:
    """Fold ``plan.source`` into ``plan.target`` and delete ``plan.source``."""
    source, target = plan.source, plan.target
    if await brand_is_represented(db, source):
        raise_error(status.HTTP_409_CONFLICT, ERR_BRAND_MERGE_SOURCE_REPRESENTED)
    if plan.conflicts:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_BRAND_MERGE_FILAMENT_CONFLICT,
            {"filament_name": plan.conflicts[0].name},
        )

    target_lines = {
        line.name.strip().casefold(): line
        for line in (
            await db.scalars(select(FilamentLine).where(FilamentLine.brand_id == target.id))
        ).all()
    }
    for line in (
        await db.scalars(select(FilamentLine).where(FilamentLine.brand_id == source.id))
    ).all():
        same_line = target_lines.get(line.name.strip().casefold())
        if same_line is None:
            line.brand_id = target.id
            continue
        await db.execute(
            update(Filament).where(Filament.line_id == line.id).values(line_id=same_line.id)
        )
        await db.execute(delete(FilamentLine).where(FilamentLine.id == line.id))
        db.expunge(line)
    await db.flush()

    for move in plan.moves:
        if move.merge_into is not None:
            continue
        filament = move.filament
        old_slug = filament.slug
        await _drop_colliding_redirects(
            db, filament_id=filament.id, from_brand_id=source.id, to_brand_id=target.id
        )
        filament.brand_id = target.id
        filament.slug = move.new_slug
        await db.flush()
        await db.execute(
            update(FilamentSlugRedirect)
            .where(
                FilamentSlugRedirect.filament_id == filament.id,
                FilamentSlugRedirect.brand_id == source.id,
            )
            .values(brand_id=target.id)
        )
        if old_slug != move.new_slug and not await _slug_taken(
            db, brand_id=target.id, slug=old_slug
        ):
            db.add(
                FilamentSlugRedirect(
                    filament_id=filament.id,
                    brand_id=target.id,
                    old_slug=old_slug,
                    reason="merge",
                )
            )
            await db.flush()

    for move in plan.moves:
        if move.merge_into is not None:
            await merge_filaments(db, source=move.filament, target=move.merge_into)

    await db.execute(delete(FilamentSlugRedirect).where(FilamentSlugRedirect.brand_id == source.id))

    await _merge_country_cells(
        db,
        model=BrandCountryCell,
        owner_key="brand_id",
        source_id=source.id,
        target_id=target.id,
        fields=("website", "shop_links", "description", "social_media_urls", "currency"),
    )
    target_months = select(BrandMonthlyAnalyticsRelease.month).where(
        BrandMonthlyAnalyticsRelease.brand_id == target.id
    )
    shared_month = await db.scalar(
        select(BrandMonthlyAnalyticsRelease.month).where(
            BrandMonthlyAnalyticsRelease.brand_id == source.id,
            BrandMonthlyAnalyticsRelease.month.in_(target_months),
        ).limit(1)
    )
    if shared_month is not None:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_BRAND_MERGE_ANALYTICS_CONFLICT,
            {"month": shared_month.strftime("%Y-%m")},
        )
    for model in (
        BrandCountryCell,
        BrandMonthlyAnalyticsRelease,
        BrandInvite,
        BrandRequest,
        EmailThread,
        MaterialMapping,
        User,
        BrandSlugRedirect,
    ):
        await db.execute(
            update(model).where(model.brand_id == source.id).values(brand_id=target.id)
        )

    source_slug = source.slug
    await db.execute(delete(Brand).where(Brand.id == source.id))
    db.expunge(source)
    db.add(BrandSlugRedirect(brand_id=target.id, old_slug=source_slug))
    await db.flush()
    await backfill_brand_qr_codes(target, db)
    logger.info("Merged brand %s into brand %s", source_slug, target.slug)


def filament_summary(
    filament: Filament, counts: dict[int, FilamentContributions]
) -> MergeFilamentSummary:
    contributions = counts.get(filament.id, FilamentContributions())
    return MergeFilamentSummary(
        id=filament.id,
        name=filament.name,
        slug=filament.slug,
        material_type=filament.material_type,
        diameter=filament.diameter,
        color_name=filament.color_name,
        color_hex=filament.color_hex,
        has_qr_code=bool(filament.qr_code),
        presets=contributions.presets,
        spools=contributions.spools,
        reviews=contributions.reviews,
    )


def rank_merge_candidates(
    source: Filament,
    pool: list[Filament],
    counts: dict[int, FilamentContributions],
    *,
    limit: int = MERGE_CANDIDATE_LIMIT,
) -> list[FilamentMergeCandidate]:
    """Records that could be the same product, the most likely first."""
    source_name = comparable_name(source.name)
    compatible = [
        filament
        for filament in pool
        if filament.id != source.id
        and same_filament_kind(
            source.material_type, source.diameter, filament.material_type, filament.diameter
        )
    ]
    compatible.sort(
        key=lambda filament: (
            not is_likely_same_filament(source, filament),
            comparable_name(filament.name) != source_name,
            not same_filament_color(
                filament.color_name, filament.color_hex, source.color_name, source.color_hex
            ),
            filament.name.casefold(),
            filament.id,
        )
    )
    return [
        FilamentMergeCandidate(
            **filament_summary(filament, counts).model_dump(),
            likely_same=is_likely_same_filament(source, filament),
        )
        for filament in compatible[:limit]
    ]


async def _brand_summary(db: AsyncSession, brand: Brand) -> MergeBrandSummary:
    filaments = await db.scalar(
        select(func.count()).select_from(Filament).where(Filament.brand_id == brand.id)
    )
    return MergeBrandSummary(
        id=brand.id,
        name=brand.name,
        slug=brand.slug,
        verified=brand.verified,
        filaments=int(filaments or 0),
    )


async def build_brand_merge_preview(
    db: AsyncSession, *, source: Brand, target: Brand
) -> BrandMergePreview:
    """What happens to each filament of ``source``, with suggested pairs."""
    unpaired = await plan_brand_merge(db, source=source, target=target, pairs={})
    needs_pair = {filament.id for filament in unpaired.conflicts}
    source_filaments = [move.filament for move in unpaired.moves] + unpaired.conflicts
    source_filaments.sort(key=lambda filament: (filament.name.casefold(), filament.id))
    target_filaments = list(
        (await db.scalars(select(Filament).where(Filament.brand_id == target.id))).all()
    )
    counts = await count_filament_contributions(
        db, [filament.id for filament in source_filaments + target_filaments]
    )

    rows = []
    for filament in source_filaments:
        candidates = rank_merge_candidates(filament, target_filaments, counts)
        suggested = next((item.id for item in candidates if item.likely_same), None)
        rows.append(
            BrandMergeFilamentRow(
                source=filament_summary(filament, counts),
                candidates=candidates,
                suggested_target_id=suggested,
                needs_pair=filament.id in needs_pair,
            )
        )
    return BrandMergePreview(
        source=await _brand_summary(db, source),
        target=await _brand_summary(db, target),
        source_represented=await brand_is_represented(db, source),
        filaments=rows,
    )


async def brand_duplicate_pairs(db: AsyncSession) -> list[BrandDuplicatePair]:
    pairs = await find_duplicate_brand_pairs(db)
    brand_ids = {brand.id for pair in pairs for brand in pair}
    count_rows = await db.execute(
        select(Filament.brand_id, func.count())
        .where(Filament.brand_id.in_(brand_ids))
        .group_by(Filament.brand_id)
    )
    counts: dict[int, int] = dict(tuple(row) for row in count_rows)

    def summary(brand: BrandIdentity) -> MergeBrandSummary:
        return MergeBrandSummary(
            id=brand.id,
            name=brand.name,
            slug=brand.slug,
            verified=brand.verified,
            filaments=counts.get(brand.id, 0),
        )

    return [BrandDuplicatePair(first=summary(left), second=summary(right)) for left, right in pairs]
