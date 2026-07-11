"""Service layer for preset version history.

Single entry point ``record_version`` decides whether a preset change
becomes a new timeline entry, folds into the latest one (squash), or is
skipped entirely (dedup). All version creation goes through here so the
``version_number`` counter stays dense and race-free.

Concurrency: ``record_version`` and ``restore_version`` take a row lock on
the parent ``Preset`` (``SELECT ... FOR UPDATE``) before reading the latest
version number, so two concurrent saves can't allocate the same number or
both create a "new" row when one should have squashed.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.preset import Preset
from app.models.preset_version import PresetVersion, PresetVersionSource
from app.services.orca_field_labels import resolve_field

logger = logging.getLogger(__name__)

# Structured Preset fields captured in each snapshot and restored on
# rollback. Intentionally excludes computed metrics (rating, success_rate,
# usage_count), moderation state, and ownership — restoring print settings
# must not reset a preset's reputation or moderation status.
_SNAPSHOT_FIELDS = (
    "name",
    "description",
    "extruder_temp",
    "bed_temp",
    "flow_rate",
    "fan_speed",
    "retraction_length",
    "retraction_speed",
)


def _canonical_hash(structured: dict, orcaslicer_settings: dict | None) -> str:
    """sha256 of a canonical JSON encoding of the effective preset payload.

    Covers BOTH the structured print fields and the orcaslicer_settings blob so
    a change to any restorable field (e.g. extruder_temp) is detected. Hashing
    only the settings blob missed structured-field edits — dedup treated them as
    no-ops and no version was recorded.
    """
    payload = json.dumps(
        {"structured": structured, "settings": orcaslicer_settings or {}},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _snapshot_structured(preset: Preset) -> dict:
    """Capture the restorable structured fields of a preset."""
    return {field: getattr(preset, field, None) for field in _SNAPSHOT_FIELDS}


async def _lock_preset(db: AsyncSession, preset_id: int) -> None:
    """Take a row lock on the parent preset to serialize version writes."""
    await db.execute(
        select(Preset.id).where(Preset.id == preset_id).with_for_update()
    )


async def get_latest_version(db: AsyncSession, preset_id: int) -> PresetVersion | None:
    """Return the most recent version for a preset, or None."""
    result = await db.execute(
        select(PresetVersion)
        .where(PresetVersion.preset_id == preset_id)
        .order_by(PresetVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_version(
    db: AsyncSession,
    preset: Preset,
    source: str,
    user_id: int | None = None,
    restored_from_version_id: int | None = None,
) -> PresetVersion | None:
    """Record a version for the current state of ``preset``.

    Returns the created or updated ``PresetVersion``, or ``None`` if the
    change was a no-op (settings identical to the latest version). Does NOT
    commit — the caller's transaction owns the commit.

    Behaviour:
      * dedup  — identical content_hash to latest -> return None
      * squash — same user, both orca_sync, latest unlabeled and within the
                 squash window -> update latest in place
      * else   — create a new version
    """
    await _lock_preset(db, preset.id)

    structured = _snapshot_structured(preset)
    new_hash = _canonical_hash(structured, preset.orcaslicer_settings)
    latest = await get_latest_version(db, preset.id)

    # 1. Dedup — nothing actually changed.
    if latest is not None and latest.content_hash == new_hash:
        return None

    # 2. Squash — fold consecutive orca_sync edits by the same user.
    if (
        latest is not None
        and source == PresetVersionSource.ORCA_SYNC
        and latest.change_source == PresetVersionSource.ORCA_SYNC
        and latest.created_by_user_id == user_id
        and not latest.label
    ):
        window = timedelta(minutes=settings.PRESET_VERSION_SQUASH_WINDOW_MINUTES)
        latest_ts = latest.updated_at
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - latest_ts < window:
            latest.snapshot_orcaslicer_settings = (
                dict(preset.orcaslicer_settings) if preset.orcaslicer_settings else None
            )
            latest.snapshot_structured = structured
            latest.content_hash = new_hash
            latest.squash_count += 1
            await db.flush()
            return latest

    # 3. New version.
    next_number = (latest.version_number + 1) if latest is not None else 1
    version = PresetVersion(
        preset_id=preset.id,
        version_number=next_number,
        snapshot_orcaslicer_settings=(
            dict(preset.orcaslicer_settings) if preset.orcaslicer_settings else None
        ),
        snapshot_structured=structured,
        content_hash=new_hash,
        change_source=source,
        restored_from_version_id=restored_from_version_id,
        created_by_user_id=user_id,
    )
    db.add(version)
    await db.flush()
    return version


async def list_versions(
    db: AsyncSession,
    preset_id: int,
    labeled_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PresetVersion], int]:
    """Return (versions desc by number, total count). Snapshots not loaded here."""
    from sqlalchemy import func as sa_func

    base = select(PresetVersion).where(PresetVersion.preset_id == preset_id)
    if labeled_only:
        base = base.where(PresetVersion.label != "")

    count_q = select(sa_func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    rows = (
        await db.execute(
            base.order_by(PresetVersion.version_number.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def get_version(
    db: AsyncSession, preset_id: int, version_id: int
) -> PresetVersion | None:
    """Fetch a single version (with snapshots) scoped to its preset."""
    result = await db.execute(
        select(PresetVersion).where(
            PresetVersion.id == version_id,
            PresetVersion.preset_id == preset_id,
        )
    )
    return result.scalar_one_or_none()


async def set_label(
    db: AsyncSession,
    version: PresetVersion,
    label: str,
    description: str | None,
) -> PresetVersion:
    """Set or clear a version's label. Caller validates text + ownership."""
    version.label = label
    version.label_description = description
    await db.flush()
    return version


async def restore_version(
    db: AsyncSession,
    preset: Preset,
    version: PresetVersion,
    user_id: int | None = None,
) -> PresetVersion:
    """Apply a version's snapshot to the preset and record a new version.

    Restores print settings only; metrics, moderation, and ownership are left
    untouched. Does NOT commit. The caller is responsible for triggering any
    downstream re-sync.
    """
    await _lock_preset(db, preset.id)

    # Restore the full orcaslicer_settings blob.
    preset.orcaslicer_settings = (
        dict(version.snapshot_orcaslicer_settings)
        if version.snapshot_orcaslicer_settings
        else None
    )

    # Restore the structured print fields captured in the snapshot.
    structured = version.snapshot_structured or {}
    for field in _SNAPSHOT_FIELDS:
        if field in structured:
            setattr(preset, field, structured[field])

    await db.flush()

    new_version = await record_version(
        db,
        preset,
        source=PresetVersionSource.RESTORE,
        user_id=user_id,
        restored_from_version_id=version.id,
    )
    # record_version may dedup to None if the restore is a no-op (restoring
    # the current state). In that case the latest version already reflects it.
    if new_version is None:
        latest = await get_latest_version(db, preset.id)
        assert latest is not None  # there is always at least the restored-from version
        return latest
    return new_version


def compute_diff(
    from_version: PresetVersion, to_version: PresetVersion
) -> dict:
    """Build a human-readable diff between two versions' orcaslicer_settings.

    Mapped keys land in ``changes`` with label/unit; unmapped keys land in
    ``unmapped_changes`` with raw key only.
    """
    old = from_version.snapshot_orcaslicer_settings or {}
    new = to_version.snapshot_orcaslicer_settings or {}
    keys = sorted(set(old) | set(new))

    changes: list[dict] = []
    unmapped: list[dict] = []

    for key in keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val == new_val:
            continue
        meta = resolve_field(key)
        entry = {
            "key": key,
            "old": None if old_val is None else str(old_val),
            "new": None if new_val is None else str(new_val),
        }
        if meta is not None:
            changes.append({**entry, "label": meta["label"], "unit": meta["unit"]})
        else:
            unmapped.append(entry)

    return {
        "from_version": from_version.version_number,
        "to_version": to_version.version_number,
        "changes": changes,
        "unmapped_changes": unmapped,
    }
