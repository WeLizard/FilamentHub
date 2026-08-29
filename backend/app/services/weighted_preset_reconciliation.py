"""Detect weighted-preset inputs and durably reconcile their projections."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import event, inspect, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.preset import Preset, PresetModerationStatus
from app.models.weighted_preset_refresh_job import WeightedPresetRefreshJob
from app.services import weighted_preset_service

logger = logging.getLogger(__name__)

_SESSION_AFFECTED_IDS_KEY = "weighted_preset_affected_filament_ids"

WORKER_BATCH_SIZE = 16
WORKER_IDLE_SECONDS = 2.0
RETRY_BASE_SECONDS = 5
RETRY_MAX_SECONDS = 300


@dataclass(frozen=True, slots=True)
class WeightedPresetInput:
    """The part of a preset row that can change its weighted projection."""

    filament_id: int | None
    active: bool
    is_weighted: bool
    moderation_status: PresetModerationStatus
    is_official: bool
    rating: float | None
    usage_count: int
    extruder_temp: float
    bed_temp: float
    flow_rate: float | None
    fan_speed: int | None
    retraction_length: float | None
    retraction_speed: float | None

    @property
    def contributes(self) -> bool:
        """Whether the row can currently participate in the aggregate."""
        return bool(
            self.filament_id is not None
            and self.active
            and not self.is_weighted
            and self.moderation_status == PresetModerationStatus.APPROVED
        )


def capture_weighted_preset_input(
    preset: Preset | None,
) -> WeightedPresetInput | None:
    """Take a stable before/after snapshot without retaining a mutable ORM row."""
    if preset is None:
        return None
    return WeightedPresetInput(
        filament_id=preset.filament_id,
        active=bool(preset.active),
        is_weighted=bool(preset.is_weighted),
        moderation_status=preset.moderation_status,
        is_official=bool(preset.is_official),
        rating=preset.rating,
        usage_count=preset.usage_count,
        extruder_temp=preset.extruder_temp,
        bed_temp=preset.bed_temp,
        flow_rate=preset.flow_rate,
        fan_speed=preset.fan_speed,
        retraction_length=preset.retraction_length,
        retraction_speed=preset.retraction_speed,
    )


def affected_weighted_filament_ids(
    before: WeightedPresetInput | None,
    after: WeightedPresetInput | None,
) -> frozenset[int]:
    """Return old/new aggregate cohorts whose effective input changed."""
    if before == after:
        return frozenset()

    affected: set[int] = set()
    if before is not None and before.contributes and before.filament_id is not None:
        affected.add(before.filament_id)
    if after is not None and after.contributes and after.filament_id is not None:
        affected.add(after.filament_id)
    return frozenset(affected)


async def enqueue_weighted_preset_refreshes(
    db: AsyncSession,
    filament_ids: Iterable[int],
) -> frozenset[int]:
    """Coalesce rebuild requests inside the caller's current transaction."""
    ids = frozenset(int(value) for value in filament_ids if value is not None)
    if not ids:
        return ids

    now = datetime.now(timezone.utc)
    dialect = db.get_bind().dialect.name
    for filament_id in sorted(ids):
        values = {
            "filament_id": filament_id,
            "requested_at": now,
            "next_attempt_at": now,
            "attempt_count": 0,
            "last_error": None,
        }
        statement: Any
        if dialect == "postgresql":
            statement = postgresql_insert(WeightedPresetRefreshJob).values(**values)
        elif dialect == "sqlite":
            statement = sqlite_insert(WeightedPresetRefreshJob).values(**values)
        else:  # pragma: no cover - supported deployments/tests use PostgreSQL/SQLite
            raise RuntimeError(f"Unsupported database dialect: {dialect}")
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[WeightedPresetRefreshJob.filament_id],
                set_={
                    "requested_at": now,
                    "next_attempt_at": now,
                    "attempt_count": 0,
                    "last_error": None,
                },
            )
        )
    return ids


def _snapshot_before_flush(preset: Preset) -> WeightedPresetInput:
    """Reconstruct the pre-mutation values from SQLAlchemy attribute history."""
    after = capture_weighted_preset_input(preset)
    assert after is not None
    state = inspect(preset)
    values: dict[str, Any] = {}
    for field_name in WeightedPresetInput.__dataclass_fields__:
        history = state.attrs[field_name].history
        values[field_name] = history.deleted[0] if history.deleted else getattr(after, field_name)
    return WeightedPresetInput(**values)


def _sync_refresh_upsert(connection: Any, filament_id: int, now: datetime) -> None:
    values = {
        "filament_id": filament_id,
        "requested_at": now,
        "next_attempt_at": now,
        "attempt_count": 0,
        "last_error": None,
    }
    dialect = connection.dialect.name
    statement: Any
    if dialect == "postgresql":
        statement = postgresql_insert(WeightedPresetRefreshJob).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(WeightedPresetRefreshJob).values(**values)
    else:  # pragma: no cover - supported deployments/tests use PostgreSQL/SQLite
        raise RuntimeError(f"Unsupported database dialect: {dialect}")
    connection.execute(
        statement.on_conflict_do_update(
            index_elements=[WeightedPresetRefreshJob.filament_id],
            set_={
                "requested_at": now,
                "next_attempt_at": now,
                "attempt_count": 0,
                "last_error": None,
            },
        )
    )


def _enqueue_changed_presets_before_flush(
    session: Session,
    _flush_context: Any,
    _instances: Any,
) -> None:
    """Put every ORM preset mutation through one transactional classifier."""
    affected: set[int] = set()
    for instance in session.new:
        if isinstance(instance, Preset):
            affected.update(
                affected_weighted_filament_ids(
                    None,
                    capture_weighted_preset_input(instance),
                )
            )
    for instance in session.dirty:
        if isinstance(instance, Preset):
            affected.update(
                affected_weighted_filament_ids(
                    _snapshot_before_flush(instance),
                    capture_weighted_preset_input(instance),
                )
            )
    for instance in session.deleted:
        if isinstance(instance, Preset):
            affected.update(
                affected_weighted_filament_ids(
                    capture_weighted_preset_input(instance),
                    None,
                )
            )

    if not affected:
        return
    now = datetime.now(timezone.utc)
    connection = session.connection()
    for filament_id in sorted(affected):
        _sync_refresh_upsert(connection, filament_id, now)
    session.info.setdefault(_SESSION_AFFECTED_IDS_KEY, set()).update(affected)


def _clear_rolled_back_refresh_ids(session: Session) -> None:
    session.info.pop(_SESSION_AFFECTED_IDS_KEY, None)


def install_weighted_preset_reconciliation() -> None:
    """Install the process-wide ORM hook once for every sync/async session."""
    marker = "_filamenthub_weighted_reconciliation_installed"
    if getattr(Session, marker, False):
        return
    event.listen(Session, "before_flush", _enqueue_changed_presets_before_flush)
    event.listen(Session, "after_rollback", _clear_rolled_back_refresh_ids)
    setattr(Session, marker, True)


def take_committed_weighted_refresh_ids(db: AsyncSession) -> frozenset[int]:
    """Return and clear IDs committed by the request before immediate draining."""
    return frozenset(db.info.pop(_SESSION_AFFECTED_IDS_KEY, set()))


async def reconcile_weighted_preset_change(
    db: AsyncSession,
    *,
    before: WeightedPresetInput | None,
    preset: Preset | None,
) -> frozenset[int]:
    """Classify one mutation and enqueue every affected aggregate cohort."""
    affected = affected_weighted_filament_ids(
        before,
        capture_weighted_preset_input(preset),
    )
    return await enqueue_weighted_preset_refreshes(db, affected)


def _retry_delay(attempt_count: int) -> timedelta:
    seconds = min(
        RETRY_MAX_SECONDS,
        RETRY_BASE_SECONDS * (2 ** max(0, attempt_count - 1)),
    )
    return timedelta(seconds=seconds)


@dataclass(frozen=True, slots=True)
class RefreshRunResult:
    processed: int = 0
    succeeded: int = 0
    failed: int = 0


async def process_weighted_preset_refreshes(
    db: AsyncSession,
    *,
    max_jobs: int = WORKER_BATCH_SIZE,
    filament_ids: Iterable[int] | None = None,
) -> RefreshRunResult:
    """Process a bounded set of due jobs, locking each coalescing key once."""
    if max_jobs <= 0:
        return RefreshRunResult()

    requested_ids = (
        frozenset(int(value) for value in filament_ids) if filament_ids is not None else None
    )
    if requested_ids is not None and not requested_ids:
        return RefreshRunResult()

    processed = succeeded = failed = 0
    while processed < max_jobs:
        now = datetime.now(timezone.utc)
        query = (
            select(WeightedPresetRefreshJob)
            .where(WeightedPresetRefreshJob.next_attempt_at <= now)
            .order_by(
                WeightedPresetRefreshJob.next_attempt_at,
                WeightedPresetRefreshJob.requested_at,
                WeightedPresetRefreshJob.filament_id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if requested_ids is not None:
            query = query.where(WeightedPresetRefreshJob.filament_id.in_(requested_ids))
        job = (await db.execute(query)).scalar_one_or_none()
        if job is None:
            break

        processed += 1
        try:
            async with db.begin_nested():
                await weighted_preset_service.create_or_update_weighted_preset(
                    job.filament_id,
                    db,
                    min_presets_count=4,
                )
        except Exception as exc:  # noqa: BLE001 - the durable row is the retry boundary
            failed += 1
            job.attempt_count += 1
            job.last_error = type(exc).__name__[:100]
            job.next_attempt_at = now + _retry_delay(job.attempt_count)
            try:
                await db.commit()
            except Exception:  # noqa: BLE001 - the already committed job remains due
                await db.rollback()
                logger.warning(
                    "Could not persist weighted preset retry state for filament %s",
                    job.filament_id,
                    exc_info=True,
                )
                break
            logger.warning(
                "Weighted preset refresh failed for filament %s; retry %s scheduled",
                job.filament_id,
                job.attempt_count,
                exc_info=True,
            )
        else:
            succeeded += 1
            await db.delete(job)
            await db.commit()

    return RefreshRunResult(
        processed=processed,
        succeeded=succeeded,
        failed=failed,
    )


async def process_weighted_preset_refreshes_best_effort(
    db: AsyncSession,
    filament_ids: Iterable[int],
) -> RefreshRunResult:
    """Try request-local refresh after commit without failing the mutation."""
    ids = frozenset(filament_ids)
    try:
        return await process_weighted_preset_refreshes(
            db,
            max_jobs=min(len(ids), WORKER_BATCH_SIZE),
            filament_ids=ids,
        )
    except Exception:  # noqa: BLE001 - the durable job remains for the worker
        await db.rollback()
        logger.warning("Immediate weighted preset refresh failed", exc_info=True)
        return RefreshRunResult(failed=1)


async def run_weighted_preset_refresh_worker(session_factory: Any) -> None:
    """Continuously drain due refreshes in bounded batches across app workers."""
    while True:
        processed = 0
        try:
            async with session_factory() as db:
                result = await process_weighted_preset_refreshes(
                    db,
                    max_jobs=WORKER_BATCH_SIZE,
                )
                processed = result.processed
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a later poll retries durable rows
            logger.warning("Weighted preset refresh worker failed", exc_info=True)

        await asyncio.sleep(0 if processed >= WORKER_BATCH_SIZE else WORKER_IDLE_SECONDS)
