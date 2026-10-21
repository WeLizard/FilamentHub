"""Account-scoped Spoolman vendor and filament transport resources."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload

from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.spool_compat_resource import SpoolCompatResource, SpoolCompatResourceExtra
from app.models.user_saved_preset import UserSavedPreset
from app.services.spool_compat_query_service import text_filter
from app.services.spool_compat_resource_service import (
    CompatExtraValidationError,
    CompatRevisionConflict,
    create_import_ref,
    ensure_catalog_ref,
    get_ref,
    patch_resource_extra,
    update_import_ref,
    validate_declared_extra,
)

router = APIRouter(tags=["spool_compat"])
Kind = Literal["vendor", "filament"]


def _legacy():
    # This router is included by spool_compat after its helpers are defined.
    from app.api.v1.endpoints import spool_compat
    return spool_compat


def _omit_none(payload: dict) -> dict:
    """Spoolman leaves absent optional resource fields out of its JSON object."""
    return {key: value for key, value in payload.items() if value is not None}


async def prepare_projection(db: AsyncSession, *, user_id: int, refs: list[SpoolCompatResource]) -> None:
    """Load a response's material graph and private fields in bounded batches."""
    visible = {
        ref.id: ref for ref in refs
        if ref.user_id is None or ref.user_id == user_id
    }
    filament_ids = {ref.filament_id for ref in visible.values() if ref.filament_id is not None}
    filaments = {
        item.id: item for item in (await db.scalars(
            select(Filament).where(Filament.id.in_(filament_ids)).options(
                joinedload(Filament.brand), selectinload(Filament.presets)
            )
        )).all()
    } if filament_ids else {}
    brand_ids = {item.brand_id for item in filaments.values() if item.brand_id is not None}
    vendor_wires = set()
    for ref in visible.values():
        source = ref.latest_payload or {}
        vendor = source.get("vendor")
        wire_id = source.get("vendor_id") or (vendor.get("id") if isinstance(vendor, dict) else None)
        if isinstance(wire_id, int):
            vendor_wires.add(wire_id)
    vendors = (await db.scalars(select(SpoolCompatResource).where(
        SpoolCompatResource.kind == "vendor",
        or_(SpoolCompatResource.user_id.is_(None), SpoolCompatResource.user_id == user_id),
        or_(SpoolCompatResource.wire_id.in_(vendor_wires),
            and_(SpoolCompatResource.source_kind == "catalog",
                 SpoolCompatResource.brand_id.in_(brand_ids))),
    ))).all() if vendor_wires or brand_ids else []
    mapped_brands = {ref.brand_id for ref in vendors if ref.source_kind == "catalog"}
    for brand_id in sorted(brand_ids - mapped_brands):
        vendors.append(await ensure_catalog_ref(db, kind="vendor", catalog_id=brand_id))
    visible.update({ref.id: ref for ref in vendors})
    all_brand_ids = {ref.brand_id for ref in visible.values() if ref.brand_id is not None}
    brands = {
        item.id: item for item in (await db.scalars(
            select(Brand).where(Brand.id.in_(all_brand_ids))
        )).all()
    } if all_brand_ids else {}
    extras = {
        row.resource_id: deepcopy(row.extra)
        for row in (await db.scalars(select(SpoolCompatResourceExtra).where(
            SpoolCompatResourceExtra.user_id == user_id,
            SpoolCompatResourceExtra.resource_id.in_(visible),
        ))).all()
    } if visible else {}
    db.info["spool_compat_projection"] = {
        "user_id": user_id, "refs": visible, "filaments": filaments, "brands": brands,
        "vendors_by_wire": {ref.wire_id: ref for ref in visible.values() if ref.kind == "vendor"},
        "vendors_by_brand": {ref.brand_id: ref for ref in visible.values()
                             if ref.kind == "vendor" and ref.source_kind == "catalog"},
        "extras": extras, "payloads": {},
    }


async def _projection_context(db: AsyncSession, user_id: int, ref: SpoolCompatResource):
    context = db.info.get("spool_compat_projection")
    if context is None or context["user_id"] != user_id or ref.id not in context["refs"]:
        await prepare_projection(db, user_id=user_id, refs=[ref])
        context = db.info["spool_compat_projection"]
    return context


async def project_vendor(db: AsyncSession, *, user_id: int, ref: SpoolCompatResource) -> dict:
    legacy = _legacy()
    if ref.kind != "vendor" or (ref.user_id is not None and ref.user_id != user_id):
        raise ValueError("invisible vendor reference")
    context = await _projection_context(db, user_id, ref)
    if ref.id in context["payloads"]:
        return deepcopy(context["payloads"][ref.id])
    brand = context["brands"].get(ref.brand_id)
    if brand is not None:
        payload = legacy._vendor_payload(brand)
    else:
        source = deepcopy(ref.latest_payload or {})
        payload = {
            "id": ref.wire_id, "registered": legacy._iso(ref.created_at),
            "name": source.get("name"), "comment": source.get("comment"),
            "empty_spool_weight": source.get("empty_spool_weight"),
            "external_id": source.get("external_id"), "extra": {},
        }
    payload["id"] = ref.wire_id
    payload["external_id"] = ref.external_id if ref.source_kind == "import" else None
    payload["extra"] = deepcopy(context["extras"].get(ref.id, {}))
    payload = _omit_none(payload)
    context["payloads"][ref.id] = deepcopy(payload)
    return payload


async def project_filament(db: AsyncSession, *, user_id: int, ref: SpoolCompatResource) -> dict:
    legacy = _legacy()
    if ref.kind != "filament" or (ref.user_id is not None and ref.user_id != user_id):
        raise ValueError("invisible filament reference")
    context = await _projection_context(db, user_id, ref)
    if ref.id in context["payloads"]:
        return deepcopy(context["payloads"][ref.id])
    filament = context["filaments"].get(ref.filament_id)
    source = deepcopy(ref.latest_payload or {}) if ref.source_kind == "import" else {}
    payload = legacy._filament_payload(filament, ref.wire_id)
    if filament is not None and filament.price_per_kg is not None and filament.spool_weight:
        payload["price"] = round(filament.price_per_kg * filament.spool_weight / 1000, 4)
    if filament is None:
        payload.update({key: source.get(key, payload.get(key)) for key in (
            "name", "material", "price", "density", "diameter", "weight",
            "spool_weight", "article_number", "comment", "settings_extruder_temp",
            "settings_bed_temp", "color_hex", "multi_color_hexes", "multi_color_direction",
        )})
        payload["registered"] = legacy._iso(ref.created_at)
        vendor_value = source.get("vendor")
        vendor_id = source.get("vendor_id") or (vendor_value.get("id") if isinstance(vendor_value, dict) else None)
        vendor_payload = None
        if vendor_id is not None:
            try:
                vendor_ref = context["vendors_by_wire"].get(int(vendor_id))
            except (TypeError, ValueError):
                vendor_ref = None
            vendor_payload = await project_vendor(db, user_id=user_id, ref=vendor_ref) if vendor_ref else None
            payload["vendor"] = vendor_payload
        elif isinstance(vendor_value, dict):
            vendor_payload = vendor_value
            payload["vendor"] = vendor_payload
        if payload.get("spool_weight") is None and vendor_payload is not None:
            payload["spool_weight"] = vendor_payload.get("empty_spool_weight")
    elif filament.brand_id is not None:
        vendor_ref = context["vendors_by_brand"][filament.brand_id]
        payload["vendor"] = await project_vendor(db, user_id=user_id, ref=vendor_ref)
    payload["id"] = ref.wire_id
    payload["external_id"] = ref.external_id if ref.source_kind == "import" else None
    payload["extra"] = deepcopy(context["extras"].get(ref.id, {}))
    payload = _omit_none(payload)
    context["payloads"][ref.id] = deepcopy(payload)
    return payload


async def _authorized(db: AsyncSession, api_key: str | None):
    legacy = _legacy()
    user, _device = await legacy._resolve_user_and_device(db, api_key)
    return user


def _print_settings(data: dict) -> tuple[float | None, float | None] | None:
    values = []
    for key in ("settings_extruder_temp", "settings_bed_temp"):
        value = data.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))
                                  or not math.isfinite(value) or value < 0 or value > 500):
            raise ValueError("invalid print settings")
        values.append(float(value) if value is not None else None)
    return tuple(values) if any(value is not None for value in values) else None


def _validate_payload(kind: Kind, data: dict) -> None:
    def walk(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)
    if "name" in data and (not isinstance(data["name"], str) or len(data["name"]) > 200):
        raise ValueError("invalid name")
    if "extra" in data and data["extra"] is not None and not isinstance(data["extra"], dict):
        raise ValueError("invalid extra")
    if "external_id" in data and data["external_id"] is not None and (
        not isinstance(data["external_id"], str) or len(data["external_id"]) > 255
    ):
        raise ValueError("invalid external ID")
    number_fields = ("price", "density", "diameter", "weight", "spool_weight")
    if kind == "filament":
        for key in number_fields:
            value = data.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or value < 0):
                raise ValueError("invalid numeric field")
        _print_settings(data)


async def _ensure_print_draft(db: AsyncSession, *, user_id: int,
                              ref: SpoolCompatResource, data: dict) -> None:
    values = _print_settings(data)
    if values is None:
        return
    extruder, bed = values
    external_id = f"spoolman:filament:{ref.id}"
    if await db.scalar(select(Preset.id).where(Preset.user_id == user_id,
                                               Preset.external_id == external_id)) is not None:
        return
    settings: dict = {"import_provider": "spoolman", "import_requires_review": True,
                      "import_ref_id": ref.id,
                      "import_missing_fields": [name for name, value in
                                                (("extruder_temp", extruder), ("bed_temp", bed)) if value is None]}
    if extruder is not None:
        settings["nozzle_temperature"] = [str(extruder)]
        settings["nozzle_temperature_initial_layer"] = [str(extruder)]
    if bed is not None:
        settings["hot_plate_temp"] = [str(bed)]
        settings["hot_plate_temp_initial_layer"] = [str(bed)]
    draft = Preset(filament_id=ref.filament_id, user_id=user_id, created_by_user_id=user_id,
                   name=str(data.get("name") or f"Imported filament {ref.wire_id}")[:200],
                   is_official=False, is_weighted=False,
                   extruder_temp=extruder or 0.0, bed_temp=bed or 0.0,
                   orcaslicer_settings=settings, moderation_status=PresetModerationStatus.PENDING,
                   active=False, source="spoolman", external_id=external_id)
    db.add(draft)
    await db.flush()
    db.add(UserSavedPreset(user_id=user_id, preset_id=draft.id, sync=False))


def _response_error(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"message": message})


async def _list(db: AsyncSession, *, user_id: int, kind: Kind, request: Request) -> JSONResponse:
    params = request.query_params
    name = params.get("name")
    external_id = params.get("external_id")
    try:
        limit = int(params["limit"]) if "limit" in params else None
        offset = int(params.get("offset", "0"))
    except ValueError:
        return _response_error(400, "Invalid limit or offset.")
    if offset < 0 or (limit is not None and limit < 0):
        return _response_error(400, "Invalid limit or offset.")
    model = Brand if kind == "vendor" else Filament
    column = SpoolCompatResource.brand_id if kind == "vendor" else SpoolCompatResource.filament_id
    # Ensure primary transport mappings before asking SQL for visible rows.
    catalog_ids = (await db.scalars(select(model.id).where(model.active.is_(True),
        ~exists(select(SpoolCompatResource.id).where(
            SpoolCompatResource.kind == kind,
            SpoolCompatResource.source_kind == "catalog", column == model.id))))).all()
    for catalog_id in catalog_ids:
        await ensure_catalog_ref(db, kind=kind, catalog_id=catalog_id)
    stmt = (select(SpoolCompatResource).outerjoin(model, column == model.id)
            .where(SpoolCompatResource.kind == kind,
                   or_(SpoolCompatResource.user_id.is_(None), SpoolCompatResource.user_id == user_id),
                   or_(and_(SpoolCompatResource.source_kind == "catalog", model.active.is_(True)),
                       SpoolCompatResource.source_kind == "import")))
    if name is not None:
        condition = text_filter(func.coalesce(model.name,
            SpoolCompatResource.latest_payload["name"].as_string()), name)
        if condition is not None:
            stmt = stmt.where(condition)
    if external_id is not None:
        stmt = stmt.where(SpoolCompatResource.external_id == external_id)
    if kind == "filament":
        stmt = stmt.where(or_(SpoolCompatResource.source_kind == "import", model.active.is_(True)))
        material = params.get("material")
        if material is not None:
            condition = text_filter(func.coalesce(model.material_type,
                SpoolCompatResource.latest_payload["material"].as_string()), material)
            if condition is not None:
                stmt = stmt.where(condition)
        vendor_id = params.get("vendor.id") or params.get("vendor_id")
        if vendor_id is not None:
            try:
                ids = [int(part) for part in vendor_id.split(",")]
            except ValueError:
                return _response_error(400, "Invalid vendor ID.")
            vendor_refs = (await db.scalars(select(SpoolCompatResource).where(
                SpoolCompatResource.kind == "vendor", SpoolCompatResource.wire_id.in_(ids),
                or_(SpoolCompatResource.user_id.is_(None), SpoolCompatResource.user_id == user_id),
            ))).all()
            brand_ids = [ref.brand_id for ref in vendor_refs if ref.brand_id is not None]
            stmt = stmt.where(or_(model.brand_id.in_(brand_ids),
                SpoolCompatResource.latest_payload["vendor_id"].as_integer().in_(ids),
                SpoolCompatResource.latest_payload["vendor"]["id"].as_integer().in_(ids)))
        vendor_name = params.get("vendor_name") or params.get("vendor.name")
        if vendor_name is not None:
            vendor_ref = aliased(SpoolCompatResource)
            vendor_brand = aliased(Brand)
            vendor_catalog_name = text_filter(vendor_brand.name, vendor_name)
            vendor_import_name = text_filter(vendor_ref.latest_payload["name"].as_string(), vendor_name)
            if vendor_catalog_name is None:
                vendor_name = None
            else:
                vendor_wire_ids = select(vendor_ref.wire_id).where(
                    vendor_ref.kind == "vendor",
                    or_(vendor_ref.user_id.is_(None), vendor_ref.user_id == user_id),
                    or_(vendor_import_name,
                        vendor_ref.brand_id.in_(select(vendor_brand.id).where(
                            vendor_catalog_name))))
                stmt = stmt.outerjoin(Brand, model.brand_id == Brand.id).where(or_(
                    text_filter(Brand.name, vendor_name),
                    text_filter(SpoolCompatResource.latest_payload["vendor"]["name"].as_string(), vendor_name),
                    SpoolCompatResource.latest_payload["vendor_id"].as_integer().in_(vendor_wire_ids),
                    SpoolCompatResource.latest_payload["vendor"]["id"].as_integer().in_(vendor_wire_ids)))
    stmt = stmt.order_by(SpoolCompatResource.wire_id)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    refs = (await db.scalars(stmt)).all()
    await prepare_projection(db, user_id=user_id, refs=refs)
    payloads = [await (project_vendor(db, user_id=user_id, ref=ref) if kind == "vendor" else
                       project_filament(db, user_id=user_id, ref=ref)) for ref in refs]
    await db.commit()
    return JSONResponse(content=payloads)


async def _get(db: AsyncSession, *, user_id: int, kind: Kind, wire_id: int) -> JSONResponse:
    ref = await get_ref(db, user_id=user_id, kind=kind, wire_id=wire_id)
    if ref is None:
        return _response_error(404, f"No {kind} with ID {wire_id} found.")
    db.info.pop("spool_compat_projection", None)
    payload = await (project_vendor(db, user_id=user_id, ref=ref) if kind == "vendor" else
                     project_filament(db, user_id=user_id, ref=ref))
    await db.commit()
    return JSONResponse(content=payload)


async def _create(db: AsyncSession, *, user_id: int, kind: Kind, request: Request) -> JSONResponse:
    try:
        data = await request.json()
    except ValueError:
        return _response_error(400, "Invalid JSON object.")
    if not isinstance(data, dict):
        return _response_error(400, "Expected JSON object.")
    try:
        _validate_payload(kind, data)
    except ValueError:
        return _response_error(400, "Invalid resource data.")
    if data.get("extra") is not None:
        try:
            await validate_declared_extra(db, user_id=user_id, kind=kind, extra=data["extra"])
        except CompatExtraValidationError as exc:
            return _response_error(400, str(exc))
    if kind == "filament":
        vendor_value = data.get("vendor")
        vendor_id = data.get("vendor_id") or (vendor_value.get("id") if isinstance(vendor_value, dict) else None)
        if vendor_id is not None:
            try:
                vendor_ref = await get_ref(db, user_id=user_id, kind="vendor", wire_id=int(vendor_id))
            except (TypeError, ValueError):
                vendor_ref = None
            if vendor_ref is None:
                return _response_error(404, "Vendor not found.")
    external_id = data.get("external_id")
    if external_id is not None and not isinstance(external_id, str):
        return _response_error(400, "Invalid external ID.")
    try:
        ref = await create_import_ref(db, user_id=user_id, kind=kind, payload=data,
            source_namespace="spoolman", external_id=external_id)
    except ValueError:
        return _response_error(400, "Invalid import data.")
    if isinstance(data.get("extra"), dict) and data["extra"]:
        await patch_resource_extra(db, user_id=user_id, resource_id=ref.id, extra=data["extra"])
    if kind == "filament":
        await _ensure_print_draft(db, user_id=user_id, ref=ref, data=data)
    db.info.pop("spool_compat_projection", None)
    payload = await (project_vendor(db, user_id=user_id, ref=ref) if kind == "vendor" else
                     project_filament(db, user_id=user_id, ref=ref))
    await db.commit()
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)


async def _patch(db: AsyncSession, *, user_id: int, kind: Kind, wire_id: int, request: Request) -> JSONResponse:
    ref = await get_ref(db, user_id=user_id, kind=kind, wire_id=wire_id, for_update=True)
    if ref is None:
        return _response_error(404, f"No {kind} with ID {wire_id} found.")
    try:
        data = await request.json()
    except ValueError:
        return _response_error(400, "Invalid JSON object.")
    if not isinstance(data, dict):
        return _response_error(400, "Expected JSON object.")
    try:
        _validate_payload(kind, data)
    except ValueError:
        return _response_error(400, "Invalid resource data.")
    extra = data.pop("extra", None)
    if extra is not None and not isinstance(extra, dict):
        return _response_error(400, "Extra must be an object.")
    if extra is not None:
        try:
            await validate_declared_extra(db, user_id=user_id, kind=kind, extra=extra)
        except CompatExtraValidationError as exc:
            return _response_error(400, str(exc))
    if ref.source_kind != "import" and data:
        return _response_error(403, "Catalog resource editing is not allowed.")
    if ref.source_kind == "import" and data:
        if ref.filament_id is not None or ref.brand_id is not None:
            return _response_error(409, "Resolved catalog facts cannot be changed through an import.")
        if kind == "filament" and {"settings_extruder_temp", "settings_bed_temp"} & data.keys():
            draft_id = await db.scalar(select(Preset.id).where(
                Preset.user_id == user_id, Preset.external_id == f"spoolman:filament:{ref.id}"
            ))
            if draft_id is not None and any(
                data[key] != (ref.latest_payload or {}).get(key)
                for key in ("settings_extruder_temp", "settings_bed_temp") if key in data
            ):
                return _response_error(409, "Review the existing imported print preset before changing its settings.")
        latest = deepcopy(ref.latest_payload or {})
        latest.update(data)
        if kind == "filament":
            vendor_value = latest.get("vendor")
            vendor_id = latest.get("vendor_id") or (vendor_value.get("id") if isinstance(vendor_value, dict) else None)
            if vendor_id is not None:
                try:
                    vendor_ref = await get_ref(db, user_id=user_id, kind="vendor", wire_id=int(vendor_id))
                except (TypeError, ValueError):
                    vendor_ref = None
                if vendor_ref is None:
                    return _response_error(404, "Vendor not found.")
        try:
            ref = await update_import_ref(db, user_id=user_id, import_ref_id=ref.id,
                                          payload=latest, expected_revision=ref.revision)
        except CompatRevisionConflict:
            await db.rollback()
            return _response_error(409, "Import resource was changed. Reload and retry.")
        if kind == "filament":
            await _ensure_print_draft(db, user_id=user_id, ref=ref, data=latest)
        if "external_id" in data:
            external_id = data["external_id"]
            if external_id is not None and not isinstance(external_id, str):
                return _response_error(400, "Invalid external ID.")
            ref.external_id = external_id
    if extra is not None:
        await patch_resource_extra(db, user_id=user_id, resource_id=ref.id, extra=extra)
    db.info.pop("spool_compat_projection", None)
    payload = await (project_vendor(db, user_id=user_id, ref=ref) if kind == "vendor" else
                     project_filament(db, user_id=user_id, ref=ref))
    await db.commit()
    return JSONResponse(content=payload)


async def _dispatch(db: AsyncSession, *, api_key: str | None, kind: Kind,
                    operation: str, request: Request, wire_id: int | None = None) -> JSONResponse:
    user = await _authorized(db, api_key)
    if user is None:
        return _response_error(401, "Invalid or missing API key.")
    if operation == "list":
        return await _list(db, user_id=user.id, kind=kind, request=request)
    if operation == "get":
        return await _get(db, user_id=user.id, kind=kind, wire_id=wire_id)
    if operation == "create":
        return await _create(db, user_id=user.id, kind=kind, request=request)
    return await _patch(db, user_id=user.id, kind=kind, wire_id=wire_id, request=request)


def _register_kind(kind: Kind) -> None:
    async def header_collection(request: Request, db: Annotated[AsyncSession, Depends(get_db)],
                                api_key: Annotated[str | None, Query()] = None,
                                header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> JSONResponse:
        return await _dispatch(db, api_key=api_key or header_api_key, kind=kind,
            operation="list" if request.method == "GET" else "create", request=request)

    async def header_item(wire_id: int, request: Request,
                          db: Annotated[AsyncSession, Depends(get_db)],
                          api_key: Annotated[str | None, Query()] = None,
                          header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> JSONResponse:
        return await _dispatch(db, api_key=api_key or header_api_key, kind=kind,
            operation="get" if request.method == "GET" else "patch",
            request=request, wire_id=wire_id)

    async def path_collection(api_key: str, request: Request,
                              db: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
        return await _dispatch(db, api_key=api_key, kind=kind,
            operation="list" if request.method == "GET" else "create", request=request)

    async def path_item(api_key: str, wire_id: int, request: Request,
                        db: Annotated[AsyncSession, Depends(get_db)]) -> JSONResponse:
        return await _dispatch(db, api_key=api_key, kind=kind,
            operation="get" if request.method == "GET" else "patch",
            request=request, wire_id=wire_id)

    for version in ("v1", "api/v1"):
        router.add_api_route(f"/{version}/{kind}", header_collection, methods=["GET", "POST"],
                             name=f"{kind}_{version}_collection_header")
        router.add_api_route(f"/{version}/{kind}/{{wire_id}}", header_item, methods=["GET", "PATCH"],
                             name=f"{kind}_{version}_item_header")
    for version in ("v1", "api/v1"):
        router.add_api_route(f"/{{api_key}}/{version}/{kind}", path_collection, methods=["GET", "POST"],
                             name=f"{kind}_{version}_collection_path")
        router.add_api_route(f"/{{api_key}}/{version}/{kind}/{{wire_id}}", path_item,
                             methods=["GET", "PATCH"], name=f"{kind}_{version}_item_path")


_register_kind("vendor")
_register_kind("filament")
