"""Stable Spoolman wire references without making imported data public catalog data.

The caller owns the transaction. Every private read or write takes an account ID.
"""

from __future__ import annotations

import json
from copy import deepcopy
from math import isfinite
from typing import Literal

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset
from app.models.spool_compat_resource import (
    SpoolCompatFieldDefinition,
    SpoolCompatResource,
    SpoolCompatResourceExtra,
    SpoolCompatWireCounter,
)
from app.models.user_spool import UserSpool
from app.services.spool_material_service import set_spool_filament_with_qr_guard

ResourceKind = Literal["vendor", "filament"]
FieldKind = Literal["spool", "vendor", "filament"]
_PROTECTED_SPOOL_FIELDS = frozenset({
    "rfid_tag", "tag", "tags", "printer_name", "mmu_gate_map",
    "import_provider", "import_external_ref", "import_file_sha256", "source_row",
})


class CompatResourceError(ValueError):
    """Base for transport resource failures mapped by the API layer."""


class CompatResourceNotFound(CompatResourceError):
    pass


class CompatResourceForbidden(CompatResourceError):
    pass


class CompatRevisionConflict(CompatResourceError):
    pass


class CompatFieldProtected(CompatResourceError):
    pass


class CompatExtraValidationError(CompatResourceError):
    """A declared extra field does not contain a value of its wire type."""


def _validate_declared_value(key: str, definition: dict, value: object) -> None:
    if not isinstance(value, str):
        raise CompatExtraValidationError(f"Invalid extra field for key {key}: Value is not a string.")
    if len(value) > 2**16 - 1:
        raise CompatExtraValidationError(f"Invalid extra field for key {key}: Value is too big.")
    try:
        data = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise CompatExtraValidationError(f"Invalid extra field for key {key}: Value is not valid JSON.") from exc
    field_type = definition.get("field_type")
    valid = False
    if field_type in ("text", "datetime"):
        valid = isinstance(data, str)
    elif field_type == "integer":
        # Spoolman v0.27 uses isinstance(int), including JSON booleans.
        valid = isinstance(data, int)
    elif field_type == "integer_range":
        valid = (isinstance(data, list) and len(data) == 2
                 and all(isinstance(item, int) or item is None for item in data))
    elif field_type == "float":
        valid = isinstance(data, (float, int)) and not isinstance(data, bool)
    elif field_type == "float_range":
        valid = (isinstance(data, list) and len(data) == 2
                 and all((isinstance(item, (float, int)) or item is None)
                         and not isinstance(item, bool) for item in data))
    elif field_type == "boolean":
        valid = isinstance(data, bool)
    elif field_type == "choice":
        choices = definition.get("choices")
        if definition.get("multi_choice"):
            valid = (isinstance(data, list)
                     and all(isinstance(item, str) and (choices is None or item in choices)
                             for item in data))
        else:
            valid = isinstance(data, str) and (choices is None or data in choices)
    if not valid:
        raise CompatExtraValidationError(f"Invalid extra field for key {key}: Value has the wrong type or choice.")


async def validate_declared_extra(
    db: AsyncSession, *, user_id: int, kind: FieldKind, extra: dict,
) -> None:
    """Validate persisted definitions before any entity or assignment mutation.

    Undefined fields retain historical wire behavior, including raw HH values.
    Null clears a field regardless of its declared type.
    """
    if not isinstance(extra, dict):
        raise CompatExtraValidationError("Extra must be an object.")
    if not extra:
        return
    rows = (await db.scalars(select(SpoolCompatFieldDefinition).where(
        SpoolCompatFieldDefinition.user_id == user_id,
        SpoolCompatFieldDefinition.kind == kind,
        SpoolCompatFieldDefinition.key.in_(extra.keys()),
    ).with_for_update())).all()
    for row in rows:
        value = extra[row.key]
        if value is not None:
            _validate_declared_value(row.key, row.definition, value)


def _target_column(kind: ResourceKind):
    if kind == "vendor":
        return SpoolCompatResource.brand_id, Brand
    if kind == "filament":
        return SpoolCompatResource.filament_id, Filament
    raise ValueError("invalid compatibility resource kind")


def _positive_number(value: object) -> float | None:
    try:
        number = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and isfinite(number) and number > 0 else None


def _legacy_material_payload(snapshot: dict) -> dict:
    """Expose only material facts explicitly present in a private spool import."""
    extra = snapshot.get("extra")
    fields = extra if isinstance(extra, dict) else {}
    raw = fields.get("import_original")
    original = raw if isinstance(raw, dict) else {}
    latest = {
        "legacy_spool": deepcopy(snapshot),
        "name": fields.get("display_name") or original.get("name") or f"Spool {snapshot['id']}",
        "material": fields.get("material") or original.get("material") or "Unknown",
        "weight": snapshot["initial_weight_g"],
    }
    vendor_name = fields.get("vendor") or original.get("vendor_name")
    if isinstance(vendor_name, str) and vendor_name.strip():
        latest["vendor"] = {"name": vendor_name.strip()}
    color = fields.get("color_hex") or original.get("color_hex")
    if isinstance(color, str) and color.strip():
        latest["color_hex"] = color.strip().lstrip("#")
    density = _positive_number(fields.get("density_g_cm3") or original.get("density"))
    diameter = _positive_number(fields.get("diameter_mm") or original.get("diameter"))
    if density is not None:
        latest["density"] = density
    if diameter is not None:
        latest["diameter"] = diameter
    tare = snapshot.get("empty_spool_weight_g")
    if tare is not None:
        latest["spool_weight"] = tare
    for source, target in (
        ("nozzle_temperature_c", "settings_extruder_temp"),
        ("bed_temperature_c", "settings_bed_temp"),
    ):
        temperature = _positive_number(fields.get(source))
        if temperature is not None:
            latest[target] = temperature
    return latest


async def _allocate_wire_id(db: AsyncSession, kind: ResourceKind) -> int:
    """One database counter per kind, atomically advanced across workers."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - deployed and test dialects are explicit
        raise RuntimeError("unsupported wire counter dialect")
    _, catalog_model = _target_column(kind)
    highwater = int(await db.scalar(select(func.coalesce(func.max(catalog_model.id), 0))) or 0)
    if dialect == "postgresql":
        sequence = await db.scalar(
            text("SELECT pg_get_serial_sequence(:table, 'id')"),
            {"table": catalog_model.__tablename__},
        )
        if sequence:
            quoted = ".".join(
                db.get_bind().dialect.identifier_preparer.quote(part.strip('"'))
                for part in sequence.split(".")
            )
            highwater = max(highwater, int(await db.scalar(text(f"SELECT last_value FROM {quoted}")) or 0))
    await db.execute(
        insert(SpoolCompatWireCounter)
        .values(kind=kind, next_wire_id=highwater + 1)
        .on_conflict_do_nothing(index_elements=[SpoolCompatWireCounter.kind])
    )
    wire_id = await db.scalar(
        update(SpoolCompatWireCounter)
        .where(SpoolCompatWireCounter.kind == kind)
        .values(next_wire_id=SpoolCompatWireCounter.next_wire_id + 1)
        .returning(SpoolCompatWireCounter.next_wire_id - 1)
    )
    if wire_id is None:  # pragma: no cover - counter was inserted above
        raise RuntimeError("wire counter missing")
    return int(wire_id)


async def ensure_catalog_ref(
    db: AsyncSession, *, kind: ResourceKind, catalog_id: int,
) -> SpoolCompatResource:
    """Return the one primary wire reference for a public catalog object."""
    column, model = _target_column(kind)
    if await db.get(model, catalog_id) is None:
        raise CompatResourceNotFound("catalog target not found")
    statement = select(SpoolCompatResource).where(
        SpoolCompatResource.kind == kind,
        SpoolCompatResource.source_kind == "catalog",
        column == catalog_id,
    )
    existing = await db.scalar(statement)
    if existing is not None:
        return existing
    try:
        async with db.begin_nested():
            wire_id = await _allocate_wire_id(db, kind)
            resource = SpoolCompatResource(
                kind=kind, wire_id=wire_id, source_kind="catalog",
                brand_id=catalog_id if kind == "vendor" else None,
                filament_id=catalog_id if kind == "filament" else None,
            )
            db.add(resource)
            await db.flush()
        return resource
    except IntegrityError:
        # Another worker won the unique primary-catalog-reference race.
        existing = await db.scalar(statement)
        if existing is None:
            raise
        return existing


async def create_import_ref(
    db: AsyncSession, *, user_id: int, kind: ResourceKind, payload: dict,
    source_namespace: str | None = None, external_id: str | None = None,
) -> SpoolCompatResource:
    _target_column(kind)
    if not isinstance(payload, dict):
        raise ValueError("import payload must be an object")
    if source_namespace is not None and len(source_namespace) > 80:
        raise ValueError("source namespace too long")
    if external_id is not None and len(external_id) > 255:
        raise ValueError("external ID too long")
    resource = SpoolCompatResource(
        kind=kind, wire_id=await _allocate_wire_id(db, kind),
        source_kind="import", user_id=user_id,
        original_payload=deepcopy(payload), latest_payload=deepcopy(payload),
        source_namespace=source_namespace, external_id=external_id,
    )
    db.add(resource)
    await db.flush()
    return resource


async def get_ref(
    db: AsyncSession, *, user_id: int, kind: ResourceKind, wire_id: int,
    for_update: bool = False,
) -> SpoolCompatResource | None:
    _target_column(kind)
    statement = select(SpoolCompatResource).where(
        SpoolCompatResource.kind == kind,
        SpoolCompatResource.wire_id == wire_id,
        (SpoolCompatResource.user_id.is_(None) | (SpoolCompatResource.user_id == user_id)),
    )
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return await db.scalar(statement)


async def _visible_resource(
    db: AsyncSession, *, user_id: int, resource_id: int,
) -> SpoolCompatResource:
    resource = await db.get(SpoolCompatResource, resource_id)
    if resource is None:
        raise CompatResourceNotFound("transport reference not found")
    if resource.user_id is not None and resource.user_id != user_id:
        raise CompatResourceForbidden("transport reference belongs to another account")
    return resource


async def update_import_ref(
    db: AsyncSession, *, user_id: int, import_ref_id: int,
    payload: dict, expected_revision: int,
) -> SpoolCompatResource:
    """Keep the original evidence and version the latest imported representation."""
    ref = await db.scalar(
        select(SpoolCompatResource)
        .where(SpoolCompatResource.id == import_ref_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if ref is None:
        raise CompatResourceNotFound("import reference not found")
    if ref.user_id != user_id or ref.source_kind != "import":
        raise CompatResourceForbidden("not an owned import reference")
    if ref.revision != expected_revision:
        raise CompatRevisionConflict("import revision changed")
    if not isinstance(payload, dict):
        raise ValueError("import payload must be an object")
    ref.latest_payload = deepcopy(payload)
    ref.revision += 1
    await db.flush()
    return ref


async def get_resource_extra(
    db: AsyncSession, *, user_id: int, resource_id: int,
) -> dict:
    await _visible_resource(db, user_id=user_id, resource_id=resource_id)
    row = await db.scalar(
        select(SpoolCompatResourceExtra).where(
            SpoolCompatResourceExtra.user_id == user_id,
            SpoolCompatResourceExtra.resource_id == resource_id,
        )
    )
    return deepcopy(row.extra) if row is not None else {}


async def patch_resource_extra(
    db: AsyncSession, *, user_id: int, resource_id: int, extra: dict,
) -> dict:
    await _visible_resource(db, user_id=user_id, resource_id=resource_id)
    if not isinstance(extra, dict):
        raise ValueError("extra must be an object")
    statement = select(SpoolCompatResourceExtra).where(
        SpoolCompatResourceExtra.user_id == user_id,
        SpoolCompatResourceExtra.resource_id == resource_id,
    )
    row = await db.scalar(statement.with_for_update().execution_options(populate_existing=True))
    if row is None:
        try:
            async with db.begin_nested():
                row = SpoolCompatResourceExtra(user_id=user_id, resource_id=resource_id, extra={})
                db.add(row)
                await db.flush()
        except IntegrityError:
            row = await db.scalar(statement.with_for_update().execution_options(populate_existing=True))
            if row is None:
                raise
    merged = deepcopy(row.extra or {})
    for key, value in extra.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = deepcopy(value)
    row.extra = merged
    row.revision += 1
    await db.flush()
    return deepcopy(merged)


async def list_field_defs(
    db: AsyncSession, *, user_id: int, kind: FieldKind,
) -> list[dict]:
    if kind not in ("spool", "vendor", "filament"):
        raise ValueError("invalid field kind")
    rows = (
        await db.scalars(
            select(SpoolCompatFieldDefinition)
            .where(SpoolCompatFieldDefinition.user_id == user_id,
                   SpoolCompatFieldDefinition.kind == kind)
            .order_by(SpoolCompatFieldDefinition.key)
        )
    ).all()
    return [{"key": row.key, "entity_type": row.kind, **deepcopy(row.definition)} for row in rows]


async def upsert_field_def(
    db: AsyncSession, *, user_id: int, kind: FieldKind,
    key: str, definition: dict,
) -> dict:
    if kind not in ("spool", "vendor", "filament"):
        raise ValueError("invalid field kind")
    if not key or len(key) > 100 or not isinstance(definition, dict):
        raise ValueError("invalid field definition")
    data = deepcopy(definition)
    data.pop("key", None)
    data.pop("entity_type", None)
    statement = select(SpoolCompatFieldDefinition).where(
        SpoolCompatFieldDefinition.user_id == user_id,
        SpoolCompatFieldDefinition.kind == kind,
        SpoolCompatFieldDefinition.key == key,
    )
    row = await db.scalar(statement.with_for_update().execution_options(populate_existing=True))
    if row is None:
        try:
            async with db.begin_nested():
                row = SpoolCompatFieldDefinition(user_id=user_id, kind=kind, key=key, definition=data)
                db.add(row)
                await db.flush()
        except IntegrityError:
            row = await db.scalar(statement.with_for_update().execution_options(populate_existing=True))
            if row is None:
                raise
            row.definition = data
    else:
        row.definition = data
    await db.flush()
    return {"key": key, "entity_type": kind, **deepcopy(data)}


async def delete_field_def(
    db: AsyncSession, *, user_id: int, kind: FieldKind, key: str,
) -> bool:
    if kind not in ("spool", "vendor", "filament"):
        raise ValueError("invalid field kind")
    if kind == "spool" and (key in _PROTECTED_SPOOL_FIELDS or key.startswith("import_")):
        raise CompatFieldProtected("field carries import or physical binding data")
    row = await db.scalar(
        select(SpoolCompatFieldDefinition).where(
            SpoolCompatFieldDefinition.user_id == user_id,
            SpoolCompatFieldDefinition.kind == kind,
            SpoolCompatFieldDefinition.key == key,
        ).with_for_update()
    )
    if row is None:
        return False
    if kind == "spool":
        spools = (
            await db.scalars(select(UserSpool).where(UserSpool.user_id == user_id).with_for_update())
        ).all()
        for spool in spools:
            if spool.extra and key in spool.extra:
                new_extra = dict(spool.extra)
                del new_extra[key]
                spool.extra = new_extra
    else:
        extras = (
            await db.scalars(
                select(SpoolCompatResourceExtra)
                .join(SpoolCompatResource, SpoolCompatResource.id == SpoolCompatResourceExtra.resource_id)
                .where(SpoolCompatResourceExtra.user_id == user_id,
                       SpoolCompatResource.kind == kind)
                .with_for_update()
            )
        ).all()
        for extra_row in extras:
            if key in extra_row.extra:
                new_extra = dict(extra_row.extra)
                del new_extra[key]
                extra_row.extra = new_extra
                extra_row.revision += 1
    await db.delete(row)
    await db.flush()
    return True


async def get_spool_material_context(
    db: AsyncSession, *, user_id: int, spool: UserSpool,
) -> SpoolCompatResource | None:
    """Ensure a persisted material wire reference for an existing owned spool.

    This can create a private import reference for a native unmatched spool;
    callers must commit the transaction after projecting the response.
    """
    if spool.user_id != user_id:
        raise CompatResourceForbidden("spool belongs to another account")
    if spool.compat_filament_ref_id is not None:
        ref = await _visible_resource(db, user_id=user_id, resource_id=spool.compat_filament_ref_id)
        if ref.kind != "filament":
            raise CompatResourceForbidden("spool references non-filament resource")
        return ref
    locked = (
        await db.execute(
            select(
                UserSpool.id, UserSpool.compat_filament_ref_id, UserSpool.filament_id,
                UserSpool.source, UserSpool.initial_weight_g, UserSpool.used_weight_g,
                UserSpool.price, UserSpool.lot_nr, UserSpool.comment,
                UserSpool.empty_spool_weight_g, UserSpool.extra,
            )
            .where(UserSpool.id == spool.id, UserSpool.user_id == user_id)
            .with_for_update()
        )
    ).one_or_none()
    if locked is None:
        raise CompatResourceNotFound("spool not found")
    if locked.compat_filament_ref_id is not None:
        ref = await _visible_resource(db, user_id=user_id, resource_id=locked.compat_filament_ref_id)
        if ref.kind != "filament":
            raise CompatResourceForbidden("spool references non-filament resource")
        spool.compat_filament_ref_id = ref.id
        spool.compat_filament_ref = ref
        return ref
    if locked.filament_id is not None:
        ref = await ensure_catalog_ref(db, kind="filament", catalog_id=locked.filament_id)
    else:
        extra = deepcopy(locked.extra or {})
        extra_fields = extra if isinstance(extra, dict) else {}
        snapshot = {
            "id": locked.id, "source": locked.source,
            "initial_weight_g": locked.initial_weight_g,
            "used_weight_g": locked.used_weight_g, "price": locked.price,
            "lot_nr": locked.lot_nr, "comment": locked.comment,
            "empty_spool_weight_g": locked.empty_spool_weight_g,
            "extra": extra,
        }
        ref = await create_import_ref(
            db, user_id=user_id, kind="filament", payload={"legacy_spool": snapshot},
            source_namespace=str(extra_fields.get("import_provider") or locked.source)[:80],
            external_id=str(extra_fields.get("import_external_ref") or locked.id)[:255],
        )
        ref.latest_payload = _legacy_material_payload(snapshot)
    spool.compat_filament_ref_id = ref.id
    spool.compat_filament_ref = ref
    await db.flush()
    return ref


async def resolve_import(
    db: AsyncSession, *, user_id: int, import_ref_id: int,
    target_catalog_id: int, expected_revision: int, nowait: bool = False,
) -> SpoolCompatResource:
    """Resolve an owned import; filament-linked spools retain QR protection."""
    ref = await db.scalar(
        select(SpoolCompatResource)
        .where(SpoolCompatResource.id == import_ref_id)
        .with_for_update(nowait=nowait)
        .execution_options(populate_existing=True)
    )
    if ref is None:
        raise CompatResourceNotFound("import reference not found")
    if ref.user_id != user_id or ref.source_kind != "import":
        raise CompatResourceForbidden("not an owned import")
    if ref.revision != expected_revision:
        raise CompatRevisionConflict("import revision changed")
    _, catalog_model = _target_column(ref.kind)
    if await db.get(catalog_model, target_catalog_id) is None:
        raise CompatResourceNotFound("catalog target not found")
    if ref.kind == "vendor":
        ref.brand_id = target_catalog_id
        ref.revision += 1
        await db.flush()
        return ref
    spools = (
        await db.scalars(
            select(UserSpool)
            .where(UserSpool.user_id == user_id,
                   UserSpool.compat_filament_ref_id == ref.id)
            .order_by(UserSpool.id)
            .with_for_update(nowait=nowait)
        )
    ).all()
    # A guarded spool late in the list must not leave earlier spools changed
    # if the caller catches the rejection and keeps its outer transaction.
    async with db.begin_nested():
        for spool in spools:
            await set_spool_filament_with_qr_guard(
                db, spool=spool, filament_id=target_catalog_id,
                compat_filament_ref_id=ref.id,
            )
        ref.filament_id = target_catalog_id
        ref.revision += 1
        draft = await db.scalar(
            select(Preset).where(
                Preset.user_id == user_id,
                Preset.external_id == f"spoolman:filament:{ref.id}",
                Preset.source == "spoolman",
                Preset.active.is_(False),
                Preset.filament_id.is_(None),
            ).with_for_update(nowait=True)
        )
        if draft is not None:
            settings = draft.orcaslicer_settings or {}
            if (
                settings.get("import_ref_id") == ref.id
                and settings.get("import_requires_review") is True
            ):
                draft.filament_id = target_catalog_id
        await db.flush()
    return ref


async def repoint_catalog_refs_for_merge(
    db: AsyncSession, *, kind: ResourceKind,
    source_id: int, target_id: int,
) -> None:
    """Preserve old wire identities and their separate private extras on merge."""
    if source_id == target_id:
        return
    column, model = _target_column(kind)
    if await db.get(model, source_id) is None or await db.get(model, target_id) is None:
        raise CompatResourceNotFound("merge catalog target not found")
    await ensure_catalog_ref(db, kind=kind, catalog_id=source_id)
    await ensure_catalog_ref(db, kind=kind, catalog_id=target_id)
    refs = (
        await db.scalars(
            select(SpoolCompatResource)
            .where(SpoolCompatResource.kind == kind, column == source_id)
            .order_by(SpoolCompatResource.id)
            .with_for_update()
        )
    ).all()
    for ref in refs:
        if ref.source_kind == "catalog":
            ref.source_kind = "alias"
        if kind == "vendor":
            ref.brand_id = target_id
        else:
            ref.filament_id = target_id
        if ref.source_kind == "import":
            ref.revision += 1
    await db.flush()
