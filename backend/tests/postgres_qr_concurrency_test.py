"""PostgreSQL-only QR locking, tombstone, and idempotency proofs."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.filament import Filament
from app.models.organization import Organization, OrganizationMembership
from app.models.qr_identity import (
    QrManufacturerBatch,
    QrManufacturerInstanceState,
    QrOperationReceipt,
)
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.schemas.qr_identity import ManufacturerQrBatchCreateRequest
from app.services.account_deletion import delete_user_account
from app.services.qr_identity_service import (
    claim_manufacturer_qr,
    create_manufacturer_qr_batch,
    issue_user_spool_qr,
    manufacturer_qr_payload_page,
    replace_user_spool_qr_material,
)
from tests.conftest import accepted_legal

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


async def _user(db: AsyncSession, suffix: str) -> User:
    user = User(
        email=f"qr-pg-{suffix}@example.com",
        username=f"qr_pg_{suffix}",
        password_hash="unused",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db.add(user)
    await db.flush()
    return user


async def _manufacturer_context(
    db: AsyncSession,
    suffix: str,
) -> tuple[User, Brand, Filament, str, int]:
    owner = await _user(db, f"owner_{suffix}")
    organization = Organization(
        name=f"QR PG Org {suffix}",
        slug=f"qr-pg-org-{suffix}",
        active=True,
        created_by_id=owner.id,
    )
    brand = Brand(
        name=f"QR PG Brand {suffix}",
        slug=f"qr-pg-brand-{suffix}",
        active=True,
        verified=True,
    )
    db.add_all([organization, brand])
    await db.flush()
    db.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=owner.id,
                all_brands=True,
                active=True,
            ),
            BrandTerritorialGrant(
                brand_id=brand.id,
                organization_id=organization.id,
                country=None,
                status=GrantStatus.active,
                source=GrantSource.invitation,
            ),
        ]
    )
    owner.active_organization_id = organization.id
    filament = Filament(
        brand_id=brand.id,
        name=f"QR PG Filament {suffix}",
        slug=f"qr-pg-filament-{suffix}",
        material_type="PETG",
        active=True,
        qr_code=f"FH-PG-{suffix.upper()}",
    )
    db.add(filament)
    await db.commit()
    batch = await create_manufacturer_qr_batch(
        db,
        user=owner,
        payload=ManufacturerQrBatchCreateRequest(
            brand_id=brand.id,
            mode="serialized",
            items=[{"filament_id": filament.id, "quantity": 1}],
        ),
        idempotency_key=f"pg-batch-{suffix}",
    )
    page = await manufacturer_qr_payload_page(
        db,
        user=owner,
        public_id=batch.public_id,
        offset=0,
        limit=1,
    )
    batch_id = await db.scalar(
        select(QrManufacturerBatch.id).where(QrManufacturerBatch.public_id == batch.public_id)
    )
    assert batch_id is not None
    return owner, brand, filament, page.items[0].short_code, batch_id


async def _spool(db: AsyncSession, user: User, filament: Filament) -> UserSpool:
    spool = UserSpool(
        user_id=user.id,
        filament_id=filament.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return spool


async def test_concurrent_claim_serializes_only_the_concrete_serial() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as setup:
        _owner, _brand, filament, code, batch_id = await _manufacturer_context(setup, suffix)
        first_user = await _user(setup, f"claim_a_{suffix}")
        second_user = await _user(setup, f"claim_b_{suffix}")
        await setup.commit()
        first_spool = await _spool(setup, first_user, filament)
        second_spool = await _spool(setup, second_user, filament)
        actor_ids = [(first_user.id, first_spool.id), (second_user.id, second_spool.id)]

    ready = asyncio.Event()
    waiting = 0
    waiting_lock = asyncio.Lock()

    async def claim(user_id: int, spool_id: int) -> tuple[str, str | int]:
        nonlocal waiting
        async with sessions() as db:
            user = await db.get(User, user_id)
            assert user is not None
            async with waiting_lock:
                waiting += 1
                if waiting == 2:
                    ready.set()
            await ready.wait()
            try:
                result = await claim_manufacturer_qr(
                    db,
                    user=user,
                    short_code=code,
                    spool_id=spool_id,
                )
                return "ok", result.spool_id
            except HTTPException as exc:
                return "error", exc.detail["code"]

    results = await asyncio.gather(*(claim(*actor) for actor in actor_ids))
    assert sorted(result[0] for result in results) == ["error", "ok"]
    assert [result[1] for result in results if result[0] == "error"] == [
        "ERR_QR_INSTANCE_UNAVAILABLE"
    ]
    async with sessions() as verify:
        assert (
            await verify.scalar(
                select(func.count())
                .select_from(QrManufacturerInstanceState)
                .where(QrManufacturerInstanceState.batch_id == batch_id)
            )
            == 1
        )
    await engine.dispose()


async def test_concurrent_material_replacement_is_one_operation() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as setup:
        user = await _user(setup, f"replace_{suffix}")
        brand = Brand(
            name=f"QR PG Replace Brand {suffix}",
            slug=f"qr-pg-replace-brand-{suffix}",
            active=True,
        )
        setup.add(brand)
        await setup.flush()
        original = Filament(
            brand_id=brand.id,
            name=f"QR PG Original {suffix}",
            slug=f"qr-pg-original-{suffix}",
            material_type="PLA",
            active=True,
            qr_code=f"FH-PGO-{suffix.upper()}",
        )
        replacement = Filament(
            brand_id=brand.id,
            name=f"QR PG Replacement {suffix}",
            slug=f"qr-pg-replacement-{suffix}",
            material_type="PETG",
            active=True,
            qr_code=f"FH-PGR-{suffix.upper()}",
        )
        setup.add_all([original, replacement])
        await setup.flush()
        spool = await _spool(setup, user, original)
        issued = await issue_user_spool_qr(setup, user=user, spool_id=spool.id)
        user_id, spool_id, replacement_id = user.id, spool.id, replacement.id

    ready = asyncio.Event()
    waiting = 0
    waiting_lock = asyncio.Lock()

    async def replace() -> tuple[str, int]:
        nonlocal waiting
        async with sessions() as db:
            user = await db.get(User, user_id)
            assert user is not None
            async with waiting_lock:
                waiting += 1
                if waiting == 2:
                    ready.set()
            await ready.wait()
            response = await replace_user_spool_qr_material(
                db,
                user=user,
                spool_id=spool_id,
                filament_id=replacement_id,
                revision=issued.revision,
                idempotency_key=f"pg-replace-{suffix}",
                confirm_reprint=True,
            )
            return response.short_code, response.revision

    first, second = await asyncio.gather(replace(), replace())
    assert first == second
    async with sessions() as verify:
        persisted = await verify.get(UserSpool, spool_id)
        assert persisted is not None
        assert persisted.filament_id == replacement_id
        assert persisted.id is not None
        assert (
            await verify.scalar(
                select(func.count())
                .select_from(QrOperationReceipt)
                .where(
                    QrOperationReceipt.scope == f"user:{user_id}",
                    QrOperationReceipt.subject == f"spool:{spool_id}",
                )
            )
            == 1
        )
    await engine.dispose()


async def test_claim_tombstone_survives_spool_and_account_deletion() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    async with sessions() as db:
        _owner, _brand, filament, code, batch_id = await _manufacturer_context(db, suffix)
        claimant = await _user(db, f"tombstone_{suffix}")
        await db.commit()
        claimed_spool = await _spool(db, claimant, filament)
        await claim_manufacturer_qr(
            db,
            user=claimant,
            short_code=code,
            spool_id=claimed_spool.id,
        )
        await db.delete(claimed_spool)
        await db.commit()
        state = await db.scalar(
            select(QrManufacturerInstanceState).where(
                QrManufacturerInstanceState.batch_id == batch_id
            )
        )
        assert state is not None
        await db.refresh(state)
        assert state.status == "claimed"
        assert state.user_id == claimant.id
        assert state.user_spool_id is None

        claimant_id = claimant.id
        await delete_user_account(
            user=claimant,
            delete_reviews=False,
            release_brand_representation=False,
            db=db,
        )
        state = await db.scalar(
            select(QrManufacturerInstanceState).where(
                QrManufacturerInstanceState.batch_id == batch_id
            )
        )
        assert state is not None
        await db.refresh(state)
        assert state.status == "claimed"
        assert state.user_id is None
        assert state.user_spool_id is None
        assert await db.get(User, claimant_id) is None

        next_user = await _user(db, f"next_{suffix}")
        await db.commit()
        next_spool = await _spool(db, next_user, filament)
        with pytest.raises(HTTPException) as exc:
            await claim_manufacturer_qr(
                db,
                user=next_user,
                short_code=code,
                spool_id=next_spool.id,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "ERR_QR_INSTANCE_UNAVAILABLE"
    await engine.dispose()
