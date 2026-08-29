"""Regression coverage for every weighted-preset reconciliation boundary."""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.weighted_preset_refresh_job import WeightedPresetRefreshJob
from app.services import preset_version_service
from app.services.weighted_preset_reconciliation import (
    enqueue_weighted_preset_refreshes,
    take_committed_weighted_refresh_ids,
)


async def _catalog(db: AsyncSession, suffix: str) -> tuple[Filament, Filament]:
    brand = Brand(
        name=f"Reconciliation Brand {suffix}",
        slug=f"reconciliation-brand-{suffix}",
        active=True,
    )
    db.add(brand)
    await db.flush()
    first = Filament(
        brand_id=brand.id,
        name=f"First PLA {suffix}",
        slug=f"first-pla-{suffix}",
        material_type="PLA",
        active=True,
    )
    second = Filament(
        brand_id=brand.id,
        name=f"Second PLA {suffix}",
        slug=f"second-pla-{suffix}",
        material_type="PLA",
        active=True,
    )
    db.add_all([first, second])
    await db.flush()
    return first, second


def _preset(*, filament_id: int | None, user_id: int, **overrides) -> Preset:
    values = {
        "filament_id": filament_id,
        "user_id": user_id,
        "name": "Reconciliation preset",
        "extruder_temp": 210,
        "bed_temp": 60,
        "active": True,
        "moderation_status": PresetModerationStatus.APPROVED,
    }
    values.update(overrides)
    return Preset(**values)


async def _clear_jobs(db: AsyncSession) -> None:
    await db.execute(delete(WeightedPresetRefreshJob))
    await db.commit()
    take_committed_weighted_refresh_ids(db)


async def _queued_ids(db: AsyncSession) -> set[int]:
    return set(await db.scalars(select(WeightedPresetRefreshJob.filament_id)))


@pytest.mark.asyncio
async def test_explicit_null_clears_filament_instead_of_falling_back(
    auth_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
) -> None:
    first, _ = await _catalog(db_session, "explicit-null")
    draft = _preset(
        filament_id=first.id,
        user_id=auth_user.id,
        active=False,
        moderation_status=PresetModerationStatus.NOT_REQUIRED,
    )
    db_session.add(draft)
    await db_session.commit()

    response = await auth_client.patch(
        f"/api/v1/presets/{draft.id}",
        json={"filament_id": None},
    )

    assert response.status_code == 200, response.text
    assert response.json()["filament_id"] is None
    await db_session.refresh(draft)
    assert draft.filament_id is None


@pytest.mark.asyncio
async def test_active_preset_rejects_explicit_null_filament(
    auth_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
) -> None:
    first, _ = await _catalog(db_session, "active-null")
    preset = _preset(filament_id=first.id, user_id=auth_user.id)
    db_session.add(preset)
    await db_session.commit()
    await _clear_jobs(db_session)

    response = await auth_client.patch(
        f"/api/v1/presets/{preset.id}",
        json={"filament_id": None},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_PRESET_FILAMENT_REQUIRED"
    await db_session.refresh(preset)
    assert preset.filament_id == first.id


@pytest.mark.asyncio
async def test_material_move_queues_old_and_new_aggregate(
    auth_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = await _catalog(db_session, "move")
    preset = _preset(filament_id=first.id, user_id=auth_user.id)
    db_session.add(preset)
    await db_session.commit()
    await _clear_jobs(db_session)

    async def approved(*_args, **_kwargs):
        return PresetModerationStatus.APPROVED, None

    monkeypatch.setattr(
        "app.api.v1.endpoints.presets.moderate_preset",
        approved,
    )
    response = await auth_client.patch(
        f"/api/v1/presets/{preset.id}",
        json={"filament_id": second.id},
    )

    assert response.status_code == 200, response.text
    assert await _queued_ids(db_session) == {first.id, second.id}


@pytest.mark.asyncio
async def test_activation_and_admin_moderation_queue_the_material(
    auth_client: AsyncClient,
    admin_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = await _catalog(db_session, "lifecycle")
    draft = _preset(
        filament_id=None,
        user_id=auth_user.id,
        active=False,
        moderation_status=PresetModerationStatus.NOT_REQUIRED,
    )
    pending = _preset(
        filament_id=second.id,
        user_id=auth_user.id,
        name="Pending preset",
        moderation_status=PresetModerationStatus.PENDING,
    )
    db_session.add_all([draft, pending])
    await db_session.commit()
    await _clear_jobs(db_session)

    async def approved(*_args, **_kwargs):
        return PresetModerationStatus.APPROVED, None

    monkeypatch.setattr(
        "app.api.v1.endpoints.presets.moderate_preset",
        approved,
    )
    activated = await auth_client.post(
        f"/api/v1/presets/{draft.id}/activate",
        json={"filament_id": first.id},
    )
    assert activated.status_code == 200, activated.text
    assert await _queued_ids(db_session) == {first.id}

    await _clear_jobs(db_session)
    approved_response = await admin_client.post(f"/api/v1/admin/presets/{pending.id}/approve")
    assert approved_response.status_code == 200, approved_response.text
    assert await _queued_ids(db_session) == {second.id}

    await _clear_jobs(db_session)
    rejected_response = await admin_client.post(
        f"/api/v1/admin/presets/{pending.id}/reject",
        params={"reason": "unsafe"},
    )
    assert rejected_response.status_code == 200, rejected_response.text
    assert await _queued_ids(db_session) == {second.id}


@pytest.mark.asyncio
async def test_version_restore_and_orca_import_queue_changed_input(
    auth_client: AsyncClient,
    auth_user,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    filament, _ = await _catalog(db_session, "restore-import")
    preset = _preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        orcaslicer_settings={
            "fhub_source": "filamenthub",
            "nozzle_temperature": [210],
        },
        external_id="weighted-restore-import",
    )
    db_session.add(preset)
    await db_session.flush()
    from app.models.preset_version import PresetVersionSource

    first_version = await preset_version_service.record_version(
        db_session,
        preset,
        PresetVersionSource.WEB_EDIT,
        auth_user.id,
    )
    preset.extruder_temp = 225
    preset.orcaslicer_settings = {
        "fhub_source": "filamenthub",
        "nozzle_temperature": [225],
    }
    await preset_version_service.record_version(
        db_session,
        preset,
        PresetVersionSource.WEB_EDIT,
        auth_user.id,
    )
    await db_session.commit()
    assert first_version is not None
    await _clear_jobs(db_session)

    restored = await auth_client.post(
        f"/api/v1/presets/{preset.id}/versions/{first_version.id}/restore"
    )
    assert restored.status_code == 200, restored.text
    assert await _queued_ids(db_session) == {filament.id}

    await _clear_jobs(db_session)
    preset_id = preset.id
    filament_id = filament.id
    db_session.expunge_all()

    async def approved(*_args, **_kwargs):
        return PresetModerationStatus.APPROVED, None

    monkeypatch.setattr(
        "app.api.v1.endpoints.orca_sync.moderate_preset",
        approved,
    )
    imported = await auth_client.post(
        "/api/v1/orcaslicer/filaments/import",
        json={
            "profiles": [
                {
                    "name": "Reconciliation preset @fh",
                    "external_id": "weighted-restore-import",
                    "fhub_id": preset_id,
                    "filament_id": filament_id,
                    "extruder_temp": 230,
                    "bed_temp": 60,
                    "orcaslicer_settings": {
                        "fhub_id": str(preset_id),
                        "fhub_source": "filamenthub",
                        "filament_type": ["PLA"],
                        "nozzle_temperature": [230],
                    },
                }
            ]
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["results"][0]["status"] == "updated"
    assert await _queued_ids(db_session) == {filament_id}


@pytest.mark.asyncio
async def test_transaction_rollback_removes_refresh_request(
    auth_user,
    db_session: AsyncSession,
) -> None:
    filament, _ = await _catalog(db_session, "rollback")
    await db_session.commit()
    preset = _preset(filament_id=filament.id, user_id=auth_user.id)
    db_session.add(preset)
    await db_session.flush()
    assert await _queued_ids(db_session) == {filament.id}

    await db_session.rollback()

    assert await _queued_ids(db_session) == set()
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Preset).where(Preset.name == preset.name)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_concurrent_requests_coalesce_to_one_job(tmp_path) -> None:
    database = tmp_path / "weighted-coalescing.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as seed:
        first, _ = await _catalog(seed, "concurrent")
        filament_id = first.id
        await seed.commit()

    async def request_refresh() -> None:
        async with factory() as session:
            await enqueue_weighted_preset_refreshes(session, {filament_id})
            await session.commit()

    await asyncio.gather(*(request_refresh() for _ in range(8)))

    async with factory() as check:
        assert await check.scalar(select(func.count()).select_from(WeightedPresetRefreshJob)) == 1
        job = await check.get(WeightedPresetRefreshJob, filament_id)
        assert job is not None
        assert job.attempt_count == 0
    await engine.dispose()
