"""Privacy boundaries of the shared monthly brand inventory release."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Insert

from app.models.brand import Brand
from app.models.brand_monthly_analytics_release import BrandMonthlyAnalyticsRelease
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_spool import UserSpool
from app.services import brand_analytics_service


@pytest.fixture(autouse=True)
def frozen_release_month(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 5, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(brand_analytics_service, "datetime", Clock)


async def _material(db: AsyncSession, slug: str) -> Filament:
    brand = Brand(name=slug, slug=slug)
    db.add(brand)
    await db.flush()
    filament = Filament(brand_id=brand.id, name=slug, slug=slug, material_type="PLA")
    db.add(filament)
    await db.flush()
    return filament


async def _owner(db: AsyncSession, number: int | str) -> User:
    user = User(
        email=f"monthly-owner-{number}@example.com",
        username=f"monthly_owner_{number}",
        password_hash="unused-test-password",
        active=True,
    )
    db.add(user)
    await db.flush()
    return user


def _spool(user: User, filament: Filament, created_at=None) -> UserSpool:
    return UserSpool(
        user_id=user.id,
        filament_id=filament.id,
        initial_weight_g=1000,
        created_at=created_at or datetime(2026, 8, 15, tzinfo=timezone.utc),
        price=5432,
        comment="PRIVATE-INVENTORY-MARKER",
    )


@pytest.mark.asyncio
async def test_monthly_release_counts_spools_once_only_above_distinct_owner_threshold(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    suppressed = await _material(db_session, "monthly-small")
    released = await _material(db_session, "monthly-large")
    other = await _material(db_session, "monthly-other")
    owners = [await _owner(db_session, number) for number in range(10)]
    db_session.add_all([_spool(user, suppressed) for user in owners[:9]])
    # Many physical spools from the same person must never manufacture a cohort.
    db_session.add_all([_spool(owners[0], suppressed) for _ in range(15)])
    db_session.add_all([_spool(user, released) for user in owners])
    db_session.add_all([_spool(owners[0], released) for _ in range(2)])
    db_session.add_all([_spool(owners[0], other) for _ in range(20)])
    db_session.add(_spool(owners[0], released, datetime(2026, 8, 1, tzinfo=timezone.utc)))
    # Current and older months never contribute to the released physical count.
    db_session.add(_spool(owners[0], released, datetime(2026, 9, 1, tzinfo=timezone.utc)))
    db_session.add(_spool(owners[0], released, datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)))
    await db_session.commit()

    small = await admin_client.get(f"/api/v1/brands/{suppressed.brand_id}/usage")
    assert small.status_code == 200
    hidden = small.json()["monthly_registered_spools"]
    assert hidden == {
        "month": "2026-08",
        "status": "insufficient_cohort",
        "value": None,
        "captured_at": "2026-09-05T12:00:00Z",
    }
    # The other endpoint and arbitrary filter combinations cannot reveal a cell.
    same = await admin_client.get(
        f"/api/v1/brands/{suppressed.brand_id}/analytics",
        params={"country": "RU", "filament_id": released.id, "month": "2026-09"},
    )
    assert same.json() == {"scope": "global", "monthly_registered_spools": hidden}
    snapshot = await db_session.get(
        BrandMonthlyAnalyticsRelease,
        {"brand_id": suppressed.brand_id, "month": datetime(2026, 8, 1).date()},
    )
    assert snapshot.spool_count is None

    large = await admin_client.get(f"/api/v1/brands/{released.brand_id}/analytics")
    assert large.status_code == 200
    visible = large.json()["monthly_registered_spools"]
    assert visible["status"] == "available"
    assert visible["value"] == 13  # Physical spools, not the ten distinct owners.
    assert set(large.json()) == {"scope", "monthly_registered_spools"}
    assert "PRIVATE-INVENTORY-MARKER" not in large.text
    one_owner = await admin_client.get(f"/api/v1/brands/{other.brand_id}/analytics")
    assert one_owner.json()["monthly_registered_spools"]["status"] == "insufficient_cohort"

    # Freeze both suppression and successful release against late changes.
    db_session.add(_spool(owners[9], suppressed))
    original = await db_session.scalar(
        select(UserSpool).where(UserSpool.filament_id == released.id)
    )
    original.filament_id = other.id
    await db_session.commit()
    still_hidden = await admin_client.get(f"/api/v1/brands/{suppressed.brand_id}/analytics")
    still_visible = await admin_client.get(f"/api/v1/brands/{released.brand_id}/usage")
    assert still_hidden.json()["monthly_registered_spools"] == hidden
    assert still_visible.json()["monthly_registered_spools"] == visible
    assert set(still_visible.json()) == {"presets_count", "monthly_registered_spools"}


@pytest.mark.asyncio
async def test_current_or_foreign_brand_owners_cannot_fill_the_monthly_cohort(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    filament = await _material(db_session, "monthly-boundary")
    other = await _material(db_session, "monthly-boundary-other")
    owners = [await _owner(db_session, number) for number in range(10)]
    db_session.add_all([_spool(user, filament) for user in owners[:9]])
    db_session.add(_spool(owners[9], other))
    db_session.add(_spool(owners[9], filament, datetime(2026, 9, 1, tzinfo=timezone.utc)))
    db_session.add(_spool(owners[9], filament, datetime(2026, 7, 31, 23, 59, tzinfo=timezone.utc)))
    await db_session.commit()
    response = await admin_client.get(f"/api/v1/brands/{filament.brand_id}/analytics")
    assert response.json()["monthly_registered_spools"]["status"] == "insufficient_cohort"


@pytest.mark.asyncio
async def test_brand_usage_public_catalog_count_excludes_private_and_inactive_presets(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    filament = await _material(db_session, "monthly-catalog")
    for index, (status, official, active) in enumerate(
        [
            (PresetModerationStatus.APPROVED, False, True),
            (PresetModerationStatus.AUTO_GENERATED, False, True),
            (PresetModerationStatus.PENDING, True, True),
            (PresetModerationStatus.PENDING, False, True),
            (PresetModerationStatus.REJECTED, False, True),
            (PresetModerationStatus.APPROVED, False, False),
        ]
    ):
        db_session.add(
            Preset(
                filament_id=filament.id,
                name=f"Monthly catalog {index}",
                extruder_temp=210,
                bed_temp=60,
                usage_count=12345,
                moderation_status=status,
                is_official=official,
                active=active,
            )
        )
    await db_session.commit()
    response = await admin_client.get(f"/api/v1/brands/{filament.brand_id}/usage")
    assert response.status_code == 200
    assert response.json()["presets_count"] == 3
    catalog = await admin_client.get("/api/v1/presets/", params={"filament_id": filament.id})
    assert catalog.status_code == 200
    assert response.json()["presets_count"] == catalog.json()["total"]
    assert set(response.json()) == {"presets_count", "monthly_registered_spools"}
    assert response.json()["monthly_registered_spools"]["value"] is None
    assert "12345" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("today,month", [("2026-01-01", "2025-12"), ("2024-03-01", "2024-02")])
async def test_release_uses_closed_utc_calendar_month(
    admin_client: AsyncClient, db_session: AsyncSession, monkeypatch, today, month
) -> None:
    now = datetime.fromisoformat(today).replace(tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(brand_analytics_service, "datetime", Clock)
    filament = await _material(db_session, "monthly-calendar")
    for number in range(10):
        owner = await _owner(db_session, number)
        db_session.add(_spool(owner, filament, now - timedelta(microseconds=1)))
    await db_session.commit()
    response = await admin_client.get(f"/api/v1/brands/{filament.brand_id}/usage")
    metric = response.json()["monthly_registered_spools"]
    assert metric["month"] == month
    assert metric["value"] == 10


@pytest.mark.asyncio
async def test_brand_usage_not_found(admin_client: AsyncClient) -> None:
    for endpoint in ("usage", "analytics"):
        resp = await admin_client.get(f"/api/v1/brands/999999/{endpoint}")
        assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("FH_TEST_POSTGRES_URL"),
    reason="requires FH_TEST_POSTGRES_URL pointing at migrated local dev",
)
@pytest.mark.parametrize("initial_owners", [9, 10])
async def test_concurrent_monthly_release_keeps_the_committed_winner(
    monkeypatch, initial_owners
) -> None:
    """A conflicting count must neither replace nor escape the winning release."""
    engine = create_async_engine(
        os.environ["FH_TEST_POSTGRES_URL"],
        connect_args={"server_settings": {"lock_timeout": "4000"}},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    tasks = []
    inserted = asyncio.Event()
    commit_allowed = asyncio.Event()
    competing_insert = asyncio.Event()
    try:
        async with sessions() as db:
            filament = await _material(db, f"monthly-race-{suffix}")
            other = await _material(db, f"monthly-race-other-{suffix}")
            owners = [await _owner(db, f"{suffix}-{number}") for number in range(10)]
            spools = [_spool(owner, filament) for owner in owners[:initial_owners]]
            db.add_all(spools)
            await db.commit()
            brand_id, filament_id, other_id = filament.brand_id, filament.id, other.id
            last_owner_id, last_spool_id = owners[-1].id, spools[-1].id

        async with sessions() as winner, sessions() as contender:
            original_commit = winner.commit
            original_execute = contender.execute

            async def hold_winning_commit():
                inserted.set()
                await asyncio.wait_for(commit_allowed.wait(), timeout=5)
                await original_commit()

            async def observe_competing_insert(statement, *args, **kwargs):
                if isinstance(statement, Insert):
                    competing_insert.set()
                return await original_execute(statement, *args, **kwargs)

            monkeypatch.setattr(winner, "commit", hold_winning_commit)
            monkeypatch.setattr(contender, "execute", observe_competing_insert)
            tasks.append(
                asyncio.create_task(
                    brand_analytics_service.monthly_registered_spools(
                        winner, brand_id=brand_id, global_scope=True
                    )
                )
            )
            await asyncio.wait_for(inserted.wait(), timeout=5)

            # The winning row is uncommitted while a second request observes a
            # different cohort. Preserve all generated local fixtures.
            async with sessions() as db:
                if initial_owners == 9:
                    owner = await db.get(User, last_owner_id)
                    material = await db.get(Filament, filament_id)
                    db.add(_spool(owner, material))
                else:
                    spool = await db.get(UserSpool, last_spool_id)
                    spool.filament_id = other_id
                await db.commit()

            tasks.append(
                asyncio.create_task(
                    brand_analytics_service.monthly_registered_spools(
                        contender, brand_id=brand_id, global_scope=True
                    )
                )
            )
            await asyncio.wait_for(competing_insert.wait(), timeout=5)
            assert not tasks[0].done()
            assert not tasks[1].done()
            commit_allowed.set()
            first, second = await asyncio.wait_for(asyncio.gather(*tasks), timeout=6)
            assert first == second
            assert first.status == ("available" if initial_owners == 10 else "insufficient_cohort")
            assert first.value == (10 if initial_owners == 10 else None)

        async with sessions() as db:
            again = await brand_analytics_service.monthly_registered_spools(
                db, brand_id=brand_id, global_scope=True
            )
            assert again == first
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(BrandMonthlyAnalyticsRelease)
                    .where(BrandMonthlyAnalyticsRelease.brand_id == brand_id)
                )
                == 1
            )
    finally:
        commit_allowed.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
