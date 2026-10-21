"""Account-owned review and resolution of compatibility imports."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user import User
from app.models.user_spool import UserSpool
from app.services.spool_compat_resource_service import (
    CompatResourceForbidden,
    CompatResourceNotFound,
    CompatRevisionConflict,
    get_ref,
    resolve_import,
)

router = APIRouter()


class ImportTarget(BaseModel):
    filament_id: int = Field(gt=0)


class ImportResolution(ImportTarget):
    expected_revision: int = Field(ge=1)
    preview_token: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


async def _owned_import(
    db: AsyncSession, user_id: int, import_id: int, *, for_update: bool = False
) -> SpoolCompatResource:
    query = select(SpoolCompatResource).where(
            SpoolCompatResource.id == import_id,
            SpoolCompatResource.user_id == user_id,
            SpoolCompatResource.kind == "filament",
            SpoolCompatResource.source_kind == "import",
    )
    if for_update:
        query = query.with_for_update().execution_options(populate_existing=True)
    resource = await db.scalar(query)
    if resource is None:
        raise HTTPException(status_code=404, detail="ERR_NOT_FOUND")
    return resource


def _target_facts(target: Filament) -> dict:
    return {
        "id": target.id, "name": target.name,
        "brand_name": target.brand.name if target.brand else None,
        "material_type": target.material_type, "color_hex": target.color_hex,
        "diameter": target.diameter, "density": target.density,
        "weight": target.spool_weight, "spool_weight": target.empty_spool_weight_g,
    }


def _preview_token(detail: dict, target: Filament) -> str:
    snapshot = {
        "import_id": detail["id"], "revision": detail["revision"],
        "imported": detail["material"],
        "spool_ids": sorted(spool["id"] for spool in detail["spools"]),
        "target": _target_facts(target),
    }
    return hashlib.sha256(json.dumps(
        snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


async def _detail(db: AsyncSession, user_id: int, resource: SpoolCompatResource) -> dict:
    payload = resource.latest_payload or {}
    vendor_name = None
    vendor_id = payload.get("vendor_id")
    if isinstance(vendor_id, int):
        vendor = await get_ref(db, user_id=user_id, kind="vendor", wire_id=vendor_id)
        if vendor is not None:
            if vendor.latest_payload:
                vendor_name = vendor.latest_payload.get("name")
            elif vendor.brand_id is not None:
                from app.models.brand import Brand

                brand = await db.get(Brand, vendor.brand_id)
                vendor_name = brand.name if brand is not None else None
    if vendor_name is None:
        vendor_name = payload.get("brand_name") or payload.get("vendor")
        if isinstance(vendor_name, dict):
            vendor_name = vendor_name.get("name")
    spools = (
        await db.scalars(
            select(UserSpool)
            .where(
                UserSpool.user_id == user_id,
                UserSpool.compat_filament_ref_id == resource.id,
            )
            .order_by(UserSpool.id)
        )
    ).all()
    return {
        "id": resource.id,
        "revision": resource.revision,
        "source": resource.source_namespace or "spoolman",
        "material": {
            "name": payload.get("name"),
            "brand_name": vendor_name,
            "material_type": payload.get("material"),
            "color_hex": payload.get("color_hex"),
            **{
                key: payload.get(key)
                for key in (
                    "diameter", "density", "weight", "spool_weight",
                    "settings_extruder_temp", "settings_bed_temp",
                )
            },
        },
        "spools": [
            {
                "id": spool.id,
                "name": (spool.extra or {}).get("display_name")
                or payload.get("name")
                or f"#{spool.id}",
            }
            for spool in spools
        ],
        "resolved_filament_id": resource.filament_id,
    }


@router.get("/imports/{import_id}")
async def get_import(
    import_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    resource = await _owned_import(db, current_user.id, import_id)
    return await _detail(db, current_user.id, resource)


@router.post("/imports/{import_id}/preview")
async def preview_resolution(
    import_id: int,
    body: ImportTarget,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    resource = await _owned_import(db, current_user.id, import_id)
    target = await db.scalar(
        select(Filament)
        .options(joinedload(Filament.brand))
        .where(Filament.id == body.filament_id)
    )
    if target is None:
        raise HTTPException(status_code=404, detail="ERR_NOT_FOUND")
    result = await _detail(db, current_user.id, resource)
    comparable = _target_facts(target)
    result["target_filament"] = {
        key: value for key, value in comparable.items() if key not in {"weight", "spool_weight"}
    }
    result["preview_token"] = _preview_token(result, target)
    result["differences"] = [
        {"field": key, "imported": value, "catalog": comparable[key]}
        for key, value in result["material"].items()
        if key in comparable and value != comparable[key]
    ]
    return result


@router.post("/imports/{import_id}/resolve")
async def apply_resolution(
    import_id: int,
    body: ImportResolution,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        resource = await _owned_import(db, current_user.id, import_id, for_update=True)
        # Catalog merges lock catalog rows before transport references. Never
        # wait in the reverse direction: return a retryable conflict instead.
        target = await db.scalar(select(Filament).where(Filament.id == body.filament_id)
            .options(joinedload(Filament.brand))
            .with_for_update(of=Filament, nowait=True)
            .execution_options(populate_existing=True))
        if target is None:
            raise HTTPException(status_code=404, detail="ERR_NOT_FOUND")
        if target.brand_id is not None:
            await db.scalar(select(Brand.id).where(Brand.id == target.brand_id)
                .with_for_update(nowait=True))
            await db.refresh(target.brand)
        await db.execute(select(UserSpool.id).where(
            UserSpool.user_id == current_user.id,
            UserSpool.compat_filament_ref_id == resource.id,
        ).order_by(UserSpool.id).with_for_update(nowait=True))
        if body.preview_token is not None:
            current = await _detail(db, current_user.id, resource)
            if body.preview_token != _preview_token(current, target):
                raise HTTPException(status_code=409, detail="ERR_CONFLICT")
        resource = await resolve_import(
            db,
            user_id=current_user.id,
            import_ref_id=import_id,
            target_catalog_id=body.filament_id,
            expected_revision=body.expected_revision,
        )
        result = await _detail(db, current_user.id, resource)
        await db.commit()
    except CompatResourceNotFound as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail="ERR_NOT_FOUND") from exc
    except CompatResourceForbidden as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail="ERR_FORBIDDEN") from exc
    except CompatRevisionConflict as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="ERR_CONFLICT") from exc
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise HTTPException(status_code=409, detail="ERR_CONFLICT") from exc
        raise
    except HTTPException:
        await db.rollback()
        raise
    from app.services.spool_tag_service import list_spool_tags

    from .spool_compat import (
        _broadcast_spool_event,
        _build_location_map,
        _get_user_spool,
        _project_spool,
    )

    spool_ids = [spool["id"] for spool in result["spools"]]
    locations, gates = await _build_location_map(db, current_user.id)
    tags = await list_spool_tags(db, user_id=current_user.id, spool_ids=spool_ids)
    events = []
    for spool_id in spool_ids:
        spool = await _get_user_spool(db, current_user.id, spool_id)
        if spool is not None:
            events.append(await _project_spool(db, spool, locations, gates, tags))
    await db.commit()
    for event in events:
        await _broadcast_spool_event(current_user.id, "updated", event)
    return {
        "id": result["id"],
        "revision": result["revision"],
        "filament_id": body.filament_id,
        "spool_ids": spool_ids,
    }
