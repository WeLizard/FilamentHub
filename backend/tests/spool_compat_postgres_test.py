"""PostgreSQL concurrency and account isolation for Spoolman compatibility.

Requires a migrated local-dev database. UUID-scoped fixtures are retained.
"""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints.spool_compat import (
    SpoolCreateBody,
    SpoolPatchBody,
    create_spool,
    patch_spool,
)
from app.api.v1.endpoints.spool_compat_fields import (
    EntityType,
    ExtraFieldParams,
    ExtraFieldType,
    add_or_update_field,
    get_fields,
)
from app.api.v1.endpoints.spool_import_resolution import ImportResolution, apply_resolution
from app.core.security import device_api_key_verifier
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.preset_usage_event import PresetUsageEvent
from app.models.spool_compat_resource import SpoolCompatResource, SpoolCompatResourceExtra
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool
from app.services.spool_compat_resource_service import (
    create_import_ref,
    ensure_catalog_ref,
    get_ref,
    get_resource_extra,
    patch_resource_extra,
    resolve_import,
)
from tests.conftest import accepted_legal

POSTGRES_URL = os.getenv("FH_TEST_POSTGRES_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not POSTGRES_URL,
        reason="requires FH_TEST_POSTGRES_URL pointing at migrated local dev",
    ),
]


async def _wait_for_lock(sessions: async_sessionmaker, pid: int) -> None:
    """Observe the actual PostgreSQL lock wait before releasing the other session."""
    async with sessions() as observer:
        for _ in range(100):
            wait = await observer.scalar(
                text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            )
            if wait == "Lock":
                return
            await asyncio.sleep(0.05)
    pytest.fail(f"backend {pid} never waited on the held compatibility row")


async def _seed(sessions: async_sessionmaker, *, accounts: int = 1):
    suffix = uuid4().hex[:12]
    async with sessions() as db:
        brand = Brand(
            name=f"Compat PG brand {suffix}", slug=f"compat-pg-brand-{suffix}",
            verified=True, active=True,
        )
        filament = Filament(
            brand=brand, name=f"Compat PG PLA {suffix}",
            slug=f"compat-pg-pla-{suffix}", material_type="PLA",
            color_name="Blue", color_hex="#2233CC", diameter=1.75,
            density=1.24, spool_weight=1000.0, active=True,
        )
        users = []
        devices = []
        for index in range(accounts):
            raw_key = f"compat_pg_key_{suffix}_{index}"
            user = User(
                email=f"compat-pg-{suffix}-{index}@example.com",
                username=f"compat_pg_{suffix}_{index}",
                password_hash="unused", active=True, email_verified=True,
                **accepted_legal(),
            )
            device = UserPrinterDevice(
                user=user, name=f"Compat PG device {suffix}-{index}",
                device_fingerprint=f"compat-pg-{suffix}-{index}",
                api_key=device_api_key_verifier(raw_key), supports_hh=True,
            )
            users.append(user)
            devices.append((device, raw_key))
        db.add_all([brand, filament, *users, *(device for device, _ in devices)])
        await db.commit()
        return filament.id, [user.id for user in users], [raw_key for _, raw_key in devices]


async def test_concurrent_catalog_ref_creation_returns_one_wire_reference() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, _, _ = await _seed(sessions)
        async with sessions() as first, sessions() as second:
            first_ref = await ensure_catalog_ref(first, kind="filament", catalog_id=filament_id)
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            follower = asyncio.create_task(
                ensure_catalog_ref(second, kind="filament", catalog_id=filament_id)
            )
            try:
                await _wait_for_lock(sessions, second_pid)
            finally:
                await first.commit()
            second_ref = await asyncio.wait_for(follower, 10)
            await second.commit()
            assert (first_ref.id, first_ref.wire_id) == (second_ref.id, second_ref.wire_id)

        async with sessions() as verify:
            refs = (
                await verify.scalars(select(SpoolCompatResource).where(
                    SpoolCompatResource.kind == "filament",
                    SpoolCompatResource.source_kind == "catalog",
                    SpoolCompatResource.filament_id == filament_id,
                ))
            ).all()
            assert len(refs) == 1
    finally:
        await engine.dispose()


async def test_concurrent_import_allocator_assigns_distinct_wire_ids() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        _, user_ids, _ = await _seed(sessions)
        async with sessions() as first, sessions() as second:
            first_ref = await create_import_ref(
                first, user_id=user_ids[0], kind="filament",
                payload={"name": "first", "material": "PLA"},
            )
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            follower = asyncio.create_task(create_import_ref(
                second, user_id=user_ids[0], kind="filament",
                payload={"name": "second", "material": "PLA"},
            ))
            try:
                await _wait_for_lock(sessions, second_pid)
            finally:
                await first.commit()
            second_ref = await asyncio.wait_for(follower, 10)
            await second.commit()
            assert first_ref.id != second_ref.id
            assert first_ref.wire_id != second_ref.wire_id

        async with sessions() as verify:
            assert await verify.scalar(select(func.count()).select_from(SpoolCompatResource).where(
                SpoolCompatResource.id.in_([first_ref.id, second_ref.id]),
            )) == 2
    finally:
        await engine.dispose()


async def test_parallel_resource_extra_patches_keep_both_keys_and_null_removal() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, user_ids, _ = await _seed(sessions)
        async with sessions() as setup:
            ref = await ensure_catalog_ref(setup, kind="filament", catalog_id=filament_id)
            await patch_resource_extra(
                setup, user_id=user_ids[0], resource_id=ref.id,
                extra={"remove_me": "old"},
            )
            await setup.commit()
            ref_id = ref.id

        async with sessions() as first, sessions() as second:
            await patch_resource_extra(
                first, user_id=user_ids[0], resource_id=ref_id,
                extra={"left": "first", "remove_me": None},
            )
            second_pid = await second.scalar(text("SELECT pg_backend_pid()"))
            follower = asyncio.create_task(patch_resource_extra(
                second, user_id=user_ids[0], resource_id=ref_id,
                extra={"right": "second"},
            ))
            try:
                await _wait_for_lock(sessions, second_pid)
            finally:
                await first.commit()
            await asyncio.wait_for(follower, 10)
            await second.commit()

        async with sessions() as verify:
            assert await get_resource_extra(
                verify, user_id=user_ids[0], resource_id=ref_id,
            ) == {"left": "first", "right": "second"}
            row = await verify.scalar(select(SpoolCompatResourceExtra).where(
                SpoolCompatResourceExtra.user_id == user_ids[0],
                SpoolCompatResourceExtra.resource_id == ref_id,
            ))
            assert row.revision == 4
    finally:
        await engine.dispose()


async def test_field_definitions_and_public_ref_extras_are_isolated_by_account() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, user_ids, keys = await _seed(sessions, accounts=2)
        async with sessions() as first:
            fields = await add_or_update_field(
                EntityType.filament, "private_note",
                ExtraFieldParams(name="Owner one", field_type=ExtraFieldType.text),
                first, api_key=keys[0],
            )
            assert any(field["key"] == "private_note" for field in fields)
            ref = await ensure_catalog_ref(first, kind="filament", catalog_id=filament_id)
            await patch_resource_extra(
                first, user_id=user_ids[0], resource_id=ref.id,
                extra={"private_note": "owner one value"},
            )
            await first.commit()
            ref_id = ref.id

        async with sessions() as second:
            assert not any(field["key"] == "private_note" for field in await get_fields(
                EntityType.filament, second, api_key=keys[1],
            ))
            assert await get_resource_extra(
                second, user_id=user_ids[1], resource_id=ref_id,
            ) == {}
            await add_or_update_field(
                EntityType.filament, "private_note",
                ExtraFieldParams(name="Owner two", field_type=ExtraFieldType.text),
                second, api_key=keys[1],
            )
            await patch_resource_extra(
                second, user_id=user_ids[1], resource_id=ref_id,
                extra={"private_note": "owner two value"},
            )
            await second.commit()

        async with sessions() as verify:
            owner_one = await get_fields(EntityType.filament, verify, api_key=keys[0])
            owner_two = await get_fields(EntityType.filament, verify, api_key=keys[1])
            assert next(field for field in owner_one if field["key"] == "private_note")["name"] == "Owner one"
            assert next(field for field in owner_two if field["key"] == "private_note")["name"] == "Owner two"
            assert await get_resource_extra(
                verify, user_id=user_ids[0], resource_id=ref_id,
            ) == {"private_note": "owner one value"}
            assert await get_resource_extra(
                verify, user_id=user_ids[1], resource_id=ref_id,
            ) == {"private_note": "owner two value"}
    finally:
        await engine.dispose()


async def test_resolution_serializes_with_live_create_spool_endpoint() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, user_ids, keys = await _seed(sessions)
        original_payload = {"name": "Imported PLA", "material": "PLA", "weight": 1000}
        async with sessions() as setup:
            ref = await create_import_ref(
                setup, user_id=user_ids[0], kind="filament",
                payload=original_payload, source_namespace="postgres_test",
            )
            existing_spool = UserSpool(
                user_id=user_ids[0], compat_filament_ref_id=ref.id,
                initial_weight_g=1000, used_weight_g=150, source="spool_compat",
            )
            setup.add(existing_spool)
            await setup.commit()
            ref_id, wire_id, existing_id = ref.id, ref.wire_id, existing_spool.id

        async with sessions() as resolver, sessions() as creator:
            held_ref = await get_ref(
                resolver, user_id=user_ids[0], kind="filament",
                wire_id=wire_id, for_update=True,
            )
            assert held_ref.id == ref_id and held_ref.filament_id is None
            creator_pid = await creator.scalar(text("SELECT pg_backend_pid()"))
            create_task = asyncio.create_task(create_spool(
                keys[0], SpoolCreateBody(filament_id=wire_id, initial_weight=900), creator,
            ))
            try:
                await _wait_for_lock(sessions, creator_pid)
                resolved = await resolve_import(
                    resolver, user_id=user_ids[0], import_ref_id=ref_id,
                    target_catalog_id=filament_id, expected_revision=1,
                )
                assert resolved.filament_id == filament_id
            finally:
                await resolver.commit()
            response = await asyncio.wait_for(create_task, 10)
            assert response.status_code == 200
            created_id = json.loads(response.body)["id"]

        async with sessions() as verify:
            persisted_ref = await verify.get(SpoolCompatResource, ref_id)
            existing = await verify.get(UserSpool, existing_id)
            created = await verify.get(UserSpool, created_id)
            assert persisted_ref.filament_id == filament_id
            assert persisted_ref.revision == 2
            assert persisted_ref.original_payload == original_payload
            assert existing.filament_id == filament_id
            assert existing.compat_filament_ref_id == ref_id
            assert (existing.initial_weight_g, existing.used_weight_g) == (1000, 150)
            assert await verify.scalar(select(func.count()).select_from(PresetUsageEvent).where(
                PresetUsageEvent.spool_id == existing_id,
            )) == 0
            assert created.filament_id == filament_id
            assert created.compat_filament_ref_id == ref_id
            assert created.initial_weight_g == 900
    finally:
        await engine.dispose()


async def test_attachment_returns_conflict_without_mutation_when_target_or_spool_is_locked() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, user_ids, keys = await _seed(sessions)
        async with sessions() as setup:
            catalog_ref = await ensure_catalog_ref(
                setup, kind="filament", catalog_id=filament_id,
            )
            import_ref = await create_import_ref(
                setup, user_id=user_ids[0], kind="filament",
                payload={"name": "Unmatched", "material": "PLA"},
            )
            existing = UserSpool(
                user_id=user_ids[0], compat_filament_ref_id=import_ref.id,
                initial_weight_g=1000, used_weight_g=125, source="spool_compat",
            )
            setup.add(existing)
            await setup.commit()
            catalog_wire, import_wire, existing_id = (
                catalog_ref.wire_id, import_ref.wire_id, existing.id,
            )

        async with sessions() as attaching, sessions() as catalog_editor:
            await get_ref(
                attaching, user_id=user_ids[0], kind="filament",
                wire_id=catalog_wire, for_update=True,
            )
            await catalog_editor.scalar(select(Filament).where(
                Filament.id == filament_id,
            ).with_for_update())
            with pytest.raises(HTTPException) as busy:
                await asyncio.wait_for(create_spool(
                    keys[0], SpoolCreateBody(filament_id=catalog_wire, initial_weight=900),
                    attaching,
                ), 3)
            assert busy.value.status_code == 409
            await catalog_editor.commit()

        async with sessions() as attaching, sessions() as spool_editor:
            await get_ref(
                attaching, user_id=user_ids[0], kind="filament",
                wire_id=import_wire, for_update=True,
            )
            await spool_editor.scalar(select(UserSpool).where(
                UserSpool.id == existing_id,
            ).with_for_update())
            with pytest.raises(HTTPException) as busy:
                await asyncio.wait_for(patch_spool(
                    keys[0], existing_id,
                    SpoolPatchBody(filament_id=import_wire, comment="should not persist"),
                    attaching,
                ), 3)
            assert busy.value.status_code == 409
            await spool_editor.commit()

        async with sessions() as verify:
            spools = (
                await verify.scalars(select(UserSpool).where(
                    UserSpool.user_id == user_ids[0],
                ))
            ).all()
            assert len(spools) == 1
            assert spools[0].id == existing_id
            assert spools[0].filament_id is None
            assert spools[0].comment is None
            assert (spools[0].initial_weight_g, spools[0].used_weight_g) == (1000, 125)
    finally:
        await engine.dispose()


async def test_import_resolution_rejects_locked_draft_without_partial_group_change() -> None:
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        filament_id, user_ids, _ = await _seed(sessions)
        async with sessions() as setup:
            ref = await create_import_ref(
                setup, user_id=user_ids[0], kind="filament",
                payload={"name": "Pending with draft", "material": "PLA"},
            )
            spool = UserSpool(
                user_id=user_ids[0], compat_filament_ref_id=ref.id,
                initial_weight_g=1000, used_weight_g=125, source="spool_compat",
            )
            draft = Preset(
                user_id=user_ids[0], name="Pending print settings", filament_id=None,
                active=False, source="spoolman", external_id=f"spoolman:filament:{ref.id}",
                extruder_temp=210, bed_temp=60,
                orcaslicer_settings={"import_ref_id": ref.id, "import_requires_review": True},
            )
            setup.add_all([spool, draft])
            await setup.commit()
            ref_id, spool_id, draft_id = ref.id, spool.id, draft.id
        async with sessions() as resolver, sessions() as draft_editor:
            user = await resolver.get(User, user_ids[0])
            await draft_editor.scalar(select(Preset.id).where(
                Preset.id == draft_id,
            ).with_for_update())
            with pytest.raises(HTTPException) as busy:
                await asyncio.wait_for(apply_resolution(
                    ref_id, ImportResolution(filament_id=filament_id, expected_revision=1),
                    user, resolver,
                ), 3)
            assert busy.value.status_code == 409
            await draft_editor.commit()
        async with sessions() as verify:
            persisted_ref = await verify.get(SpoolCompatResource, ref_id)
            persisted_spool = await verify.get(UserSpool, spool_id)
            assert persisted_ref.revision == 1 and persisted_ref.filament_id is None
            assert persisted_spool.filament_id is None
            assert persisted_spool.compat_filament_ref_id == ref_id
            assert persisted_spool.used_weight_g == 125
    finally:
        await engine.dispose()
