"""Persistent, tenant-scoped Spoolman transport identities."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.qr_identity import QrUserSpoolBinding
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user import User
from app.models.user_spool import UserSpool
from app.services.spool_compat_resource_service import (
    CompatResourceForbidden,
    CompatRevisionConflict,
    create_import_ref,
    delete_field_def,
    ensure_catalog_ref,
    get_ref,
    get_resource_extra,
    get_spool_material_context,
    list_field_defs,
    patch_resource_extra,
    repoint_catalog_refs_for_merge,
    resolve_import,
    upsert_field_def,
)
from app.services.spool_material_service import (
    apply_spool_material_identity,
    set_spool_filament_with_qr_guard,
)


async def _seed(db: AsyncSession) -> tuple[User, User, Brand, Filament]:
    first = User(email="compat-first@example.com", username="compatfirst", password_hash="unused", active=True)
    second = User(email="compat-second@example.com", username="compatsecond", password_hash="unused", active=True)
    brand = Brand(name="Compat Brand", slug="compat-brand", active=True)
    filament = Filament(
        brand=brand, name="Compat PLA", slug="compat-pla", material_type="PLA",
        color_name="Blue", color_hex="#0000FF", diameter=1.75,
        density=1.24, spool_weight=1000, active=True,
    )
    db.add_all([first, second, brand, filament])
    await db.flush()
    return first, second, brand, filament


@pytest.mark.asyncio
async def test_catalog_and_import_refs_are_stable_and_imports_private(db_session: AsyncSession) -> None:
    first, second, brand, filament = await _seed(db_session)
    vendor_ref = await ensure_catalog_ref(db_session, kind="vendor", catalog_id=brand.id)
    filament_ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=filament.id)
    assert (await ensure_catalog_ref(db_session, kind="filament", catalog_id=filament.id)).id == filament_ref.id
    imported = await create_import_ref(
        db_session, user_id=first.id, kind="filament",
        payload={"name": "Unknown PLA", "extra": {"tag": "ABCD"}},
        source_namespace="happy_hare", external_id="same-source-id",
    )
    assert imported.wire_id != filament_ref.wire_id
    assert imported.wire_id > filament.id
    assert await get_ref(db_session, user_id=first.id, kind="filament", wire_id=imported.wire_id) is imported
    assert await get_ref(db_session, user_id=second.id, kind="filament", wire_id=imported.wire_id) is None
    assert await get_ref(db_session, user_id=second.id, kind="vendor", wire_id=vendor_ref.wire_id) is not None
    assert imported.original_payload == imported.latest_payload


@pytest.mark.asyncio
async def test_locked_ref_read_refreshes_a_stale_loaded_resource(db_session: AsyncSession) -> None:
    first, _, _, filament = await _seed(db_session)
    ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=filament.id)
    await db_session.execute(
        sa.update(SpoolCompatResource).where(SpoolCompatResource.id == ref.id)
        .values(revision=7).execution_options(synchronize_session=False)
    )
    assert ref.revision == 1
    locked = await get_ref(db_session, user_id=first.id, kind="filament",
                           wire_id=ref.wire_id, for_update=True)
    assert locked is ref
    assert locked.revision == 7


def test_migration_backfills_matched_and_unmatched_spool_tare_without_rewriting_extra() -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "spool_compat_resources.py"
    spec = importlib.util.spec_from_file_location("spool_compat_resources_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    metadata = sa.MetaData()
    spools = sa.Table(
        "user_spools", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filament_id", sa.Integer),
        sa.Column("extra", sa.JSON),
        sa.Column("empty_spool_weight_g", sa.Float),
    )
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            metadata.create_all(connection)
            original = [
                {"id": 1, "filament_id": 10, "extra": {"empty_spool_weight_g": "125", "source_row": "exact"},
                 "empty_spool_weight_g": None},
                {"id": 2, "filament_id": None, "extra": {"empty_spool_weight_g": "0"},
                 "empty_spool_weight_g": None},
                {"id": 3, "filament_id": 10, "extra": {"empty_spool_weight_g": "-4"},
                 "empty_spool_weight_g": None},
                {"id": 4, "filament_id": None, "extra": {"empty_spool_weight_g": "NaN"},
                 "empty_spool_weight_g": None},
                {"id": 5, "filament_id": 10, "extra": {"empty_spool_weight_g": "300"},
                 "empty_spool_weight_g": 250},
            ]
            connection.execute(spools.insert(), original)
            assert migration._backfill_spool_tare(connection) == 2
            assert migration._backfill_spool_tare(connection) == 0
            rows = connection.execute(sa.select(spools).order_by(spools.c.id)).mappings().all()
            assert [row["empty_spool_weight_g"] for row in rows] == [125, 0, None, None, 250]
            assert [row["extra"] for row in rows] == [item["extra"] for item in original]
    finally:
        engine.dispose()


def test_migration_import_insert_explicitly_returns_generated_id() -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "spool_compat_resources.py"
    spec = importlib.util.spec_from_file_location("spool_compat_resources_insert_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    resource = sa.table(
        "spool_compat_resources",
        sa.column("id", sa.Integer()),
        sa.column("kind", sa.String()),
        sa.column("original_payload", sa.JSON()),
    )
    statement = migration._resource_insert_statement(
        resource, {"kind": "filament", "original_payload": {"source": "legacy"}}
    )
    assert "RETURNING spool_compat_resources.id" in str(
        statement.compile(dialect=postgresql.dialect())
    )
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(
                "CREATE TABLE spool_compat_resources "
                "(id INTEGER PRIMARY KEY, kind TEXT, original_payload JSON)"
            ))
            assert connection.execute(statement).scalar_one() == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_future_catalog_pk_equal_to_import_wire_id_cannot_alias_import(db_session: AsyncSession) -> None:
    first, second, brand, _ = await _seed(db_session)
    pending = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                      payload={"name": "pending"})
    future = Filament(brand_id=brand.id, name="Future PLA", slug="future-pla",
                      material_type="PLA", color_name="Black", color_hex="#000000",
                      diameter=1.75, density=1.24, spool_weight=1000, active=True)
    db_session.add(future)
    await db_session.flush()
    assert future.id == pending.wire_id
    catalog_ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=future.id)
    assert catalog_ref.wire_id != pending.wire_id
    assert (await get_ref(db_session, user_id=first.id, kind="filament", wire_id=pending.wire_id)).id == pending.id
    assert await get_ref(db_session, user_id=second.id, kind="filament", wire_id=pending.wire_id) is None
    assert (await get_ref(db_session, user_id=second.id, kind="filament", wire_id=catalog_ref.wire_id)).id == catalog_ref.id


@pytest.mark.asyncio
async def test_native_unmatched_spool_gets_persistent_private_import_context(
    db_session: AsyncSession,
) -> None:
    first, second, _, filament = await _seed(db_session)
    unmatched = UserSpool(user_id=first.id, filament_id=None, initial_weight_g=750,
                          used_weight_g=25, source="octoprint_spoolmanager", price=18.5,
                          extra={"source_row": '{"Vendor":"Unknown"}', "import_external_ref": "row-7"})
    matched = UserSpool(user_id=first.id, filament_id=filament.id,
                        initial_weight_g=1000, used_weight_g=0, source="manual")
    db_session.add_all([unmatched, matched])
    await db_session.flush()
    imported = await get_spool_material_context(db_session, user_id=first.id, spool=unmatched)
    catalog = await get_spool_material_context(db_session, user_id=first.id, spool=matched)
    assert imported.source_kind == "import" and imported.user_id == first.id
    assert imported.original_payload["legacy_spool"]["extra"]["source_row"] == '{"Vendor":"Unknown"}'
    assert unmatched.compat_import_id == imported.id
    assert matched.compat_import_id is None
    assert matched.compat_filament_ref_id == catalog.id
    assert (await get_spool_material_context(db_session, user_id=first.id, spool=unmatched)).id == imported.id
    assert await get_ref(db_session, user_id=second.id, kind="filament", wire_id=imported.wire_id) is None


@pytest.mark.asyncio
async def test_private_extras_and_field_cleanup_do_not_mutate_catalog(db_session: AsyncSession) -> None:
    first, second, _, filament = await _seed(db_session)
    ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=filament.id)
    await upsert_field_def(db_session, user_id=first.id, kind="filament", key="orca_filament_flow_ratio", definition={"name": "Flow", "field_type": "text", "default_value": ""})
    await patch_resource_extra(db_session, user_id=first.id, resource_id=ref.id, extra={"orca_filament_flow_ratio": "1.03"})
    assert (await get_resource_extra(db_session, user_id=first.id, resource_id=ref.id))["orca_filament_flow_ratio"] == "1.03"
    assert await get_resource_extra(db_session, user_id=second.id, resource_id=ref.id) == {}
    assert await patch_resource_extra(
        db_session, user_id=first.id, resource_id=ref.id,
        extra={"orca_filament_flow_ratio": None},
    ) == {}
    await patch_resource_extra(db_session, user_id=first.id, resource_id=ref.id,
                               extra={"orca_filament_flow_ratio": "1.04"})
    assert len(await list_field_defs(db_session, user_id=first.id, kind="filament")) == 1
    assert await list_field_defs(db_session, user_id=second.id, kind="filament") == []
    assert await delete_field_def(db_session, user_id=first.id, kind="filament", key="orca_filament_flow_ratio")
    assert await get_resource_extra(db_session, user_id=first.id, resource_id=ref.id) == {}
    assert filament.color_hex == "#0000FF"


@pytest.mark.asyncio
async def test_resolve_pending_material_keeps_ref_and_respects_qr_guard(db_session: AsyncSession) -> None:
    first, second, _, filament = await _seed(db_session)
    ref = await create_import_ref(db_session, user_id=first.id, kind="filament", payload={"name": "unknown"})
    spool = UserSpool(user_id=first.id, filament_id=None, compat_filament_ref_id=ref.id,
                      initial_weight_g=1000, used_weight_g=0, source="spoolman")
    db_session.add(spool)
    await db_session.flush()
    with pytest.raises(CompatResourceForbidden):
        await resolve_import(db_session, user_id=second.id, import_ref_id=ref.id,
                             target_catalog_id=filament.id, expected_revision=1)
    with pytest.raises(CompatRevisionConflict):
        await resolve_import(db_session, user_id=first.id, import_ref_id=ref.id,
                             target_catalog_id=filament.id, expected_revision=2)
    resolved = await resolve_import(db_session, user_id=first.id, import_ref_id=ref.id,
                                    target_catalog_id=filament.id, expected_revision=1)
    assert resolved.id == ref.id and resolved.wire_id == ref.wire_id
    assert resolved.original_payload == {"name": "unknown"}
    assert resolved.revision == 2
    assert spool.filament_id == filament.id
    assert (await get_spool_material_context(db_session, user_id=first.id, spool=spool)).id == ref.id


@pytest.mark.asyncio
async def test_resolve_import_attaches_only_owned_generated_inactive_draft(
    db_session: AsyncSession,
) -> None:
    first, _, _, filament = await _seed(db_session)
    ref = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                  payload={"name": "recipe", "settings_extruder_temp": 215})
    draft = Preset(
        filament_id=None, user_id=first.id, created_by_user_id=first.id,
        name="Imported recipe", extruder_temp=215, bed_temp=60,
        is_official=False, is_weighted=False,
        source="spoolman", external_id=f"spoolman:filament:{ref.id}",
        active=False, moderation_status=PresetModerationStatus.PENDING,
        orcaslicer_settings={"import_ref_id": ref.id, "import_requires_review": True},
    )
    db_session.add(draft)
    await db_session.flush()
    await resolve_import(db_session, user_id=first.id, import_ref_id=ref.id,
                         target_catalog_id=filament.id, expected_revision=1)
    assert draft.filament_id == filament.id
    assert draft.active is False
    assert draft.orcaslicer_settings["import_requires_review"] is True


@pytest.mark.asyncio
async def test_apply_spool_material_identity_clears_old_import_relation(
    db_session: AsyncSession,
) -> None:
    first, _, _, filament = await _seed(db_session)
    ref = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                  payload={"name": "old"})
    spool = UserSpool(user_id=first.id, filament_id=None, compat_filament_ref_id=ref.id,
                      initial_weight_g=1000, source="manual")
    spool.compat_filament_ref = ref
    db_session.add(spool)
    await db_session.flush()
    apply_spool_material_identity(spool, filament_id=filament.id, compat_filament_ref_id=None)
    await db_session.flush()
    assert spool.filament_id == filament.id
    assert spool.compat_filament_ref_id is None
    assert spool.compat_import_id is None


@pytest.mark.asyncio
async def test_qr_guard_rejects_compat_ref_swap_even_when_catalog_id_is_unchanged(
    db_session: AsyncSession,
) -> None:
    first, _, _, filament = await _seed(db_session)
    original = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                       payload={"name": "first"})
    replacement = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                          payload={"name": "second"})
    spool = UserSpool(user_id=first.id, filament_id=filament.id,
                      compat_filament_ref_id=original.id, initial_weight_g=1000,
                      used_weight_g=0, source="spoolman")
    db_session.add(spool)
    await db_session.flush()
    db_session.add(QrUserSpoolBinding(
        user_spool_id=spool.id, user_id=first.id, filament_id=filament.id,
        token_digest="a" * 64, token_ciphertext="opaque", state="active", revision=1,
    ))
    await db_session.flush()
    await set_spool_filament_with_qr_guard(
        db_session, spool=spool, filament_id=filament.id,
        compat_filament_ref_id=original.id,
    )
    with pytest.raises(HTTPException) as exc:
        await set_spool_filament_with_qr_guard(
            db_session, spool=spool, filament_id=filament.id,
            compat_filament_ref_id=replacement.id,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE"
    assert spool.compat_filament_ref_id == original.id


@pytest.mark.asyncio
async def test_import_resolution_rolls_back_all_spools_if_one_qr_guard_rejects(
    db_session: AsyncSession,
) -> None:
    first, _, brand, original_filament = await _seed(db_session)
    replacement = Filament(brand_id=brand.id, name="Replacement PLA", slug="replacement-pla",
                           material_type="PLA", color_name="Blue", color_hex="#0000FF",
                           diameter=1.75, density=1.24, spool_weight=1000, active=True)
    db_session.add(replacement)
    await db_session.flush()
    ref = await create_import_ref(db_session, user_id=first.id, kind="filament",
                                  payload={"name": "private"})
    ref.filament_id = original_filament.id
    ordinary = UserSpool(user_id=first.id, filament_id=original_filament.id,
                         compat_filament_ref_id=ref.id, initial_weight_g=1000, source="manual")
    guarded = UserSpool(user_id=first.id, filament_id=original_filament.id,
                        compat_filament_ref_id=ref.id, initial_weight_g=1000, source="manual")
    db_session.add_all([ordinary, guarded])
    await db_session.flush()
    db_session.add(QrUserSpoolBinding(
        user_spool_id=guarded.id, user_id=first.id, filament_id=original_filament.id,
        token_digest="b" * 64, token_ciphertext="opaque", state="active", revision=1,
    ))
    await db_session.flush()
    with pytest.raises(HTTPException):
        await resolve_import(db_session, user_id=first.id, import_ref_id=ref.id,
                             target_catalog_id=replacement.id, expected_revision=1)
    await db_session.refresh(ordinary)
    await db_session.refresh(ref)
    assert ordinary.filament_id == original_filament.id
    assert ref.filament_id == original_filament.id
    assert ref.revision == 1


@pytest.mark.asyncio
async def test_catalog_merge_keeps_old_wire_ref_as_alias(db_session: AsyncSession) -> None:
    first, _, brand, source = await _seed(db_session)
    target = Filament(brand_id=brand.id, name="Target PLA", slug="target-pla", material_type="PLA",
                      color_name="Red", color_hex="#FF0000", diameter=1.75, density=1.24,
                      spool_weight=1000, active=True)
    db_session.add(target)
    await db_session.flush()
    source_ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=source.id)
    target_ref = await ensure_catalog_ref(db_session, kind="filament", catalog_id=target.id)
    await patch_resource_extra(db_session, user_id=first.id, resource_id=source_ref.id, extra={"orca_note": "source"})
    await repoint_catalog_refs_for_merge(db_session, kind="filament", source_id=source.id, target_id=target.id)
    assert source_ref.source_kind == "alias"
    assert source_ref.filament_id == target.id
    assert target_ref.source_kind == "catalog"
    assert (await get_ref(db_session, user_id=first.id, kind="filament", wire_id=source_ref.wire_id)).id == source_ref.id
    assert (await get_resource_extra(db_session, user_id=first.id, resource_id=source_ref.id))["orca_note"] == "source"
