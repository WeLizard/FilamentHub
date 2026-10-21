"""Declared Spoolman extras use typed JSON strings; legacy extras stay permissive."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user_spool import UserSpool
from app.services.spool_compat_resource_service import (
    CompatExtraValidationError,
    delete_field_def,
    upsert_field_def,
    validate_declared_extra,
)
from tests.spool_compat_test import _seed_spool_context


@pytest.mark.asyncio
@pytest.mark.parametrize("field_type,value,valid", [
    ("text", "raw", False),
    ("text", '"raw"', True),
    ("integer", '"42"', False),
    ("integer", "42", True),
    ("float", "true", False),
    ("float", "42.5", True),
    ("boolean", '"true"', False),
    ("boolean", "true", True),
    ("integer_range", "[1, null]", True),
    ("float_range", "[1, true]", False),
    ("choice", '"missing"', False),
    ("choice", '"one"', True),
])
async def test_declared_extra_wire_types(
    db_session: AsyncSession, field_type: str, value: str, valid: bool,
) -> None:
    user, _, _ = await _seed_spool_context(db_session)
    await upsert_field_def(
        db_session, user_id=user.id, kind="spool", key="custom", definition={
            "name": "Custom", "field_type": field_type,
            "choices": ["one", "two"] if field_type == "choice" else None,
            "multi_choice": False if field_type == "choice" else None,
        },
    )
    if valid:
        await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": value})
    else:
        with pytest.raises(CompatExtraValidationError):
            await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": value})
    await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": None})
    await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"note": "raw"})
    await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"rfid_tag": "ABCD1234"})


@pytest.mark.asyncio
async def test_field_datatype_change_and_delete_change_only_future_validation(db_session: AsyncSession) -> None:
    user, _, _ = await _seed_spool_context(db_session)
    definition = {"name": "Custom", "field_type": "text"}
    await upsert_field_def(db_session, user_id=user.id, kind="spool", key="custom", definition=definition)
    await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": '"one"'})
    await upsert_field_def(db_session, user_id=user.id, kind="spool", key="custom",
                           definition={**definition, "field_type": "integer"})
    with pytest.raises(CompatExtraValidationError):
        await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": '"one"'})
    assert await delete_field_def(db_session, user_id=user.id, kind="spool", key="custom")
    await validate_declared_extra(db_session, user_id=user.id, kind="spool", extra={"custom": "raw"})


@pytest.mark.asyncio
async def test_declared_extra_rejected_before_spool_create_or_patch_mutations(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, spool, device = await _seed_spool_context(db_session)
    await upsert_field_def(db_session, user_id=user.id, kind="spool", key="memo",
                           definition={"name": "Memo", "field_type": "text"})
    await db_session.commit()
    endpoint = f"/api/v1/spool_compat/{device.api_key}/v1/spool"
    before_count = await db_session.scalar(select(func.count(UserSpool.id)))
    invalid_create = await client.post(endpoint, json={
        "filament_id": spool.filament_id, "initial_weight": 500,
        "extra": {"memo": "raw", "printer_name": json.dumps("printer")},
    })
    assert invalid_create.status_code == 400
    assert await db_session.scalar(select(func.count(UserSpool.id))) == before_count
    original_used = spool.used_weight_g
    invalid_patch = await client.patch(f"{endpoint}/{spool.id}", json={
        "used_weight": original_used + 100, "extra": {"memo": "raw"},
    })
    assert invalid_patch.status_code == 400
    await db_session.refresh(spool)
    assert spool.used_weight_g == original_used
    assert "memo" not in (spool.extra or {})
    valid = await client.patch(f"{endpoint}/{spool.id}", json={"extra": {"memo": '"stored"'}})
    assert valid.status_code == 200
    cleared = await client.patch(f"{endpoint}/{spool.id}", json={"extra": {"memo": None}})
    assert cleared.status_code == 200
    await db_session.refresh(spool)
    assert "memo" not in (spool.extra or {})


@pytest.mark.asyncio
async def test_declared_extra_rejected_before_vendor_filament_import_writes(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, _, device = await _seed_spool_context(db_session)
    base = f"/api/v1/spool_compat/{device.api_key}/v1"
    for kind in ("vendor", "filament"):
        await upsert_field_def(db_session, user_id=user.id, kind=kind, key="memo",
                               definition={"name": "Memo", "field_type": "text"})
    await db_session.commit()
    before_count = await db_session.scalar(select(func.count(SpoolCompatResource.id)))
    for kind in ("vendor", "filament"):
        invalid = await client.post(f"{base}/{kind}", json={"name": "Pending", "extra": {"memo": "raw"}})
        assert invalid.status_code == 400
        assert await db_session.scalar(select(func.count(SpoolCompatResource.id))) == before_count
        valid = await client.post(f"{base}/{kind}", json={"name": "Pending", "extra": {"memo": '"ok"'}})
        assert valid.status_code == 201
        wire_id = valid.json()["id"]
        rejected = await client.patch(f"{base}/{kind}/{wire_id}", json={
            "name": "Changed", "extra": {"memo": "raw"},
        })
        assert rejected.status_code == 400
        current = await client.get(f"{base}/{kind}/{wire_id}")
        assert current.json()["name"] == "Pending"
        assert current.json()["extra"]["memo"] == '"ok"'
        cleared = await client.patch(f"{base}/{kind}/{wire_id}", json={"extra": {"memo": None}})
        assert cleared.status_code == 200
        assert "memo" not in cleared.json()["extra"]
        before_count += 1
