from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.weighted_preset_refresh_job import WeightedPresetRefreshJob
from app.services import weighted_preset_service
from app.services.weighted_preset_reconciliation import (
    enqueue_weighted_preset_refreshes,
    process_weighted_preset_refreshes_best_effort,
)


async def _filament(db: AsyncSession, suffix: str) -> Filament:
    brand = Brand(
        name=f"Weighted Brand {suffix}",
        slug=f"weighted-brand-{suffix}",
        active=True,
    )
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name=f"Weighted PLA {suffix}",
        slug=f"weighted-pla-{suffix}",
        material_type="PLA",
        active=True,
    )
    db.add(filament)
    await db.flush()
    return filament


def _weighted(filament_id: int, suffix: str) -> Preset:
    return Preset(
        filament_id=filament_id,
        name=f"Weighted {suffix}",
        extruder_temp=210,
        bed_temp=60,
        is_weighted=True,
        active=True,
        moderation_status=PresetModerationStatus.AUTO_GENERATED,
    )


@pytest.mark.asyncio
async def test_db_forbids_two_weighted_presets_for_one_filament(
    db_session: AsyncSession,
) -> None:
    filament = await _filament(db_session, "unique")
    db_session.add(_weighted(filament.id, "first"))
    await db_session.commit()

    db_session.add(_weighted(filament.id, "second"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_weighted_service_is_idempotent_and_never_commits(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filament = await _filament(db_session, "service")
    await db_session.commit()

    async def recommended_values(_filament_id: int, _db: AsyncSession) -> dict:
        return {
            "presets_count": 4,
            "confidence": "medium",
            "extruder_temp": 212,
            "bed_temp": 62,
            "flow_rate": 1.01,
        }

    async def unexpected_commit() -> None:
        raise AssertionError("weighted service must not own the transaction")

    monkeypatch.setattr(
        weighted_preset_service,
        "get_recommended_preset_values",
        recommended_values,
    )
    monkeypatch.setattr(db_session, "commit", unexpected_commit)

    first = await weighted_preset_service.create_or_update_weighted_preset(
        filament.id,
        db_session,
        min_presets_count=0,
    )
    second = await weighted_preset_service.create_or_update_weighted_preset(
        filament.id,
        db_session,
        min_presets_count=0,
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert (
        await db_session.scalar(
            select(func.count(Preset.id)).where(
                Preset.filament_id == filament.id,
                Preset.is_weighted.is_(True),
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_immediate_failure_keeps_committed_mutation_and_durable_retry(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filament = await _filament(db_session, "retry")
    filament.name = "Committed before derived refresh"
    await enqueue_weighted_preset_refreshes(db_session, {filament.id})
    await db_session.commit()

    async def failure(*_args, **_kwargs):
        raise RuntimeError("recompute failed")

    monkeypatch.setattr(
        weighted_preset_service,
        "create_or_update_weighted_preset",
        failure,
    )

    result = await process_weighted_preset_refreshes_best_effort(
        db_session,
        {filament.id},
    )

    assert result.failed == 1
    filament_id = filament.id
    db_session.expire_all()
    persisted = await db_session.get(Filament, filament_id)
    job = await db_session.get(WeightedPresetRefreshJob, filament_id)
    assert persisted is not None
    assert persisted.name == "Committed before derived refresh"
    assert job is not None
    assert job.attempt_count == 1
    assert job.last_error == "RuntimeError"
    assert job.next_attempt_at > job.requested_at

    job.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    async def success(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        weighted_preset_service,
        "create_or_update_weighted_preset",
        success,
    )
    retry = await process_weighted_preset_refreshes_best_effort(
        db_session,
        {filament_id},
    )

    assert retry.succeeded == 1
    assert await db_session.get(WeightedPresetRefreshJob, filament_id) is None
