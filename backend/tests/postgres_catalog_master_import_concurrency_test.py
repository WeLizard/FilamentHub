"""PostgreSQL proof that an import cannot overwrite a concurrent administrator."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.catalog_master_import import apply_master_import
from app.models import Brand, BrandCountryCell, CatalogImportBatch, Filament, FilamentCountryCell
from app.models.user import User, UserRole
from app.schemas.catalog_import import CatalogImportApplyRequest, CatalogImportDraft
from app.services.catalog_master_import_service import (
    CatalogMasterImportError,
    apply_plan,
    build_plan,
    draft_digest,
    issue_confirmation,
    plan_digest,
    summarize,
    verify_confirmation,
)

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="set FH_TEST_POSTGRES_URL to run PostgreSQL concurrency tests",
    ),
]


@pytest.mark.parametrize("sheet", ["Brands", "Filaments", "BrandMarkets", "FilamentMarkets"])
async def test_second_admin_waits_then_rejects_the_stale_import(sheet: str) -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    try:
        async with sessions() as setup:
            admins = [
                User(
                    email=f"catalog-pg-{suffix}-{index}@example.com",
                    username=f"catalog_pg_{suffix}_{index}",
                    password_hash="unused",
                    active=True,
                    role=UserRole.ADMIN,
                )
                for index in range(2)
            ]
            brand = Brand(name=f"Catalog PG {suffix}", slug=f"catalog-pg-{suffix}")
            setup.add_all([*admins, brand])
            await setup.flush()
            filament = Filament(
                brand_id=brand.id,
                name=f"PLA {suffix}",
                slug=f"pla-{suffix}",
                material_type="PLA",
            )
            setup.add(filament)
            await setup.flush()
            brand_market = BrandCountryCell(brand_id=brand.id, country="TR", published=False)
            filament_market = FilamentCountryCell(
                filament_id=filament.id, country="TR", published=False
            )
            setup.add_all([brand_market, filament_market])
            await setup.commit()
            admin_ids = [admin.id for admin in admins]
            targets = {
                "Brands": (Brand, brand.id, "description"),
                "Filaments": (Filament, filament.id, "description"),
                "BrandMarkets": (BrandCountryCell, brand_market.id, "description"),
                "FilamentMarkets": (FilamentCountryCell, filament_market.id, "market_note"),
            }
            draft = CatalogImportDraft(
                filename=f"catalog-pg-{suffix}.xlsx",
                brands=[{"brand_key": "brand", "existing_brand": brand.id, "name": brand.name}],
                filaments=[
                    {
                        "filament_key": "filament",
                        "brand_key": "brand",
                        "existing_filament": filament.id,
                        "name": filament.name,
                        "material_type": "PLA",
                    }
                ],
                brand_markets=[{"brand_key": "brand", "country": "TR"}],
                filament_markets=[{"filament_key": "filament", "country": "TR"}],
            )

        draft_fields = {
            "Brands": "brands",
            "Filaments": "filaments",
            "BrandMarkets": "brand_markets",
            "FilamentMarkets": "filament_markets",
        }
        model, target_id, changed_field = targets[sheet]
        first_draft = draft.model_copy(deep=True)
        second_draft = draft.model_copy(deep=True)
        for current, value in (
            (first_draft, "First administrator"),
            (second_draft, "Second administrator"),
        ):
            getattr(current, draft_fields[sheet])[0].update(
                {changed_field: value, "overwrite": True}
            )

        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            first_plan = await build_plan(first, first_draft, admin_user_id=admin_ids[0])
            second_plan = await build_plan(second, second_draft, admin_user_id=admin_ids[1])
            assert summarize(first_plan)["error"] == summarize(second_plan)["error"] == 0
            for actor, current, plan in zip(
                admin_ids, (first_draft, second_draft), (first_plan, second_plan), strict=True
            ):
                token, _ = issue_confirmation(
                    user_id=actor,
                    draft_hash=draft_digest(current),
                    calculated_plan_digest=plan_digest(plan),
                )
                verify_confirmation(
                    token=token,
                    user_id=actor,
                    draft_hash=draft_digest(current),
                    calculated_plan_digest=plan_digest(plan),
                )

            # Both confirmed plans exist before either writer begins. The first
            # import now holds its writes uncommitted while the second applies.
            await apply_plan(first, first_draft, first_plan, admin_user_id=admin_ids[0])

            async def apply_second() -> str:
                try:
                    await apply_plan(second, second_draft, second_plan, admin_user_id=admin_ids[1])
                    await second.commit()
                    return "applied"
                except CatalogMasterImportError as exc:
                    await second.rollback()
                    return exc.code

            pending = asyncio.create_task(apply_second())
            try:
                # Observe a real PostgreSQL lock wait, rather than relying on
                # task scheduling or a sleep to imply concurrent execution.
                async with sessions() as observer:
                    async with asyncio.timeout(10):
                        while True:
                            blockers = await observer.scalar(
                                text("SELECT pg_blocking_pids(:pid)"),
                                {"pid": second_pid},
                            )
                            if first_pid in blockers:
                                break
                            if pending.done():
                                pytest.fail(f"Second import did not wait: {await pending}")
                            await asyncio.sleep(0.02)
                await first.commit()
                assert await asyncio.wait_for(pending, 10) == "ERR_CATALOG_IMPORT_STALE"
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)

        async with sessions() as verify:
            assert (
                await verify.scalar(
                    select(getattr(model, changed_field)).where(model.id == target_id)
                )
                == "First administrator"
            )
            assert (
                await verify.scalar(
                    select(func.count())
                    .select_from(CatalogImportBatch)
                    .where(CatalogImportBatch.applied_by_user_id.in_(admin_ids))
                )
                == 1
            )
    finally:
        await engine.dispose()


async def test_new_brand_race_returns_conflict_without_partial_batch() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    suffix = uuid4().hex[:12]
    try:
        async with sessions() as setup:
            admins = [
                User(
                    email=f"catalog-new-{suffix}-{index}@example.com",
                    username=f"catalog_new_{suffix}_{index}",
                    password_hash="unused",
                    active=True,
                    role=UserRole.ADMIN,
                )
                for index in range(2)
            ]
            setup.add_all(admins)
            await setup.commit()
        draft = CatalogImportDraft(
            filename=f"new-brand-{suffix}.xlsx",
            brands=[
                {"brand_key": "new", "name": f"New brand {suffix}", "slug": f"new-brand-{suffix}"}
            ],
        )
        async with sessions() as first, sessions() as second:
            first_pid = await first.scalar(text("SELECT pg_backend_pid()"))
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            first_plan = await build_plan(first, draft, admin_user_id=admins[0].id)
            second_plan = await build_plan(second, draft, admin_user_id=admins[1].id)
            assert summarize(first_plan)["create"] == summarize(second_plan)["create"] == 1
            token, _ = issue_confirmation(
                user_id=admins[1].id,
                draft_hash=draft_digest(draft),
                calculated_plan_digest=plan_digest(second_plan),
            )
            await apply_plan(first, draft, first_plan, admin_user_id=admins[0].id)

            async def apply_second() -> tuple[int, str | None]:
                try:
                    await apply_master_import(
                        CatalogImportApplyRequest(draft=draft, confirmation_token=token),
                        admin=admins[1],
                        db=second,
                    )
                    return 200, None
                except HTTPException as exc:
                    return exc.status_code, exc.detail["code"]

            pending = asyncio.create_task(apply_second())
            try:
                async with sessions() as observer:
                    async with asyncio.timeout(10):
                        while True:
                            blockers = await observer.scalar(
                                text("SELECT pg_blocking_pids(:pid)"),
                                {"pid": second_pid},
                            )
                            if first_pid in blockers:
                                break
                            if pending.done():
                                pytest.fail(f"Second import did not wait: {await pending}")
                            await asyncio.sleep(0.02)
                await first.commit()
                assert await asyncio.wait_for(pending, 10) == (409, "ERR_CATALOG_IMPORT_STALE")
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        async with sessions() as verify:
            assert (
                await verify.scalar(
                    select(func.count())
                    .select_from(Brand)
                    .where(Brand.slug == f"new-brand-{suffix}")
                )
                == 1
            )
            assert (
                await verify.scalar(
                    select(func.count())
                    .select_from(CatalogImportBatch)
                    .where(
                        CatalogImportBatch.applied_by_user_id.in_([admin.id for admin in admins])
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()
