"""Tag reader registry and live event sockets of the Spoolman-compatible API.

Spoolman 0.27 added a tag scan relay: ``GET /tag/reader`` lists readers seen
recently and two websockets carry scans to whoever is watching. Clients also
use ``/tag/reader`` as the capability probe for native tags, so it is exposed
only together with the rest of that contract: scan answers that always name
``matched_spool_id`` and ``matched_filament_id``, tag links on spools, and the
root websocket that streams every change.

Unlike Spoolman, every route here is bound to a device key, so one account's
readers, scans and changes are never visible to another.
"""

from __future__ import annotations

import base64
import binascii
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, WebSocket, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.brand import Brand
from app.models.preset_usage_event import PresetUsageEventType
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.spool_compat_resource_service import create_import_ref, ensure_catalog_ref
from app.services.spool_tag_service import SpoolTagConflict, link_spool_tag
from app.services.spool_usage_service import record_spool_usage
from app.services.tag_payload import DecodedTag, decode_tag
from app.services.tag_scan_relay import list_readers

from .spool_compat_external import _brand_key, match_catalog_filament
from .spool_compat_ws import ALL_CHANGES_POOL, TAG_SCAN_POOL

logger = logging.getLogger(__name__)

router = APIRouter(tags=["spool_compat"])

TAG_NAMESPACE = "tag"


def decode_scan(tag_format: str | None, payload_b64: str | None, uid: str) -> DecodedTag | None:
    """Decode a scan's raw tag contents; anything unreadable is simply not decoded."""
    if not tag_format or not payload_b64:
        return None
    try:
        contents = base64.b64decode(payload_b64, validate=True)
        uid_bytes = bytes.fromhex(uid)
    except (binascii.Error, ValueError):
        return None
    return decode_tag(tag_format, contents, uid_bytes)


async def _import_vendor_wire_id(db: AsyncSession, user_id: int, vendor_name: str) -> int:
    """The vendor a tag names: the catalog brand when there is one, else the account's own."""
    key = _brand_key(vendor_name)
    for brand_id, name in (
        await db.execute(select(Brand.id, Brand.name).where(Brand.active.is_(True)))
    ).all():
        if _brand_key(name) == key:
            return (await ensure_catalog_ref(db, kind="vendor", catalog_id=brand_id)).wire_id
    known = (
        await db.scalars(
            select(SpoolCompatResource).where(
                SpoolCompatResource.kind == "vendor",
                SpoolCompatResource.source_kind == "import",
                SpoolCompatResource.user_id == user_id,
            )
        )
    ).all()
    for ref in known:
        if _brand_key((ref.latest_payload or {}).get("name")) == key:
            return ref.wire_id
    created = await create_import_ref(
        db, user_id=user_id, kind="vendor", payload={"name": vendor_name},
        source_namespace=TAG_NAMESPACE,
    )
    return created.wire_id


async def _filament_ref_for_tag(
    db: AsyncSession, user_id: int, decoded: DecodedTag
) -> SpoolCompatResource:
    """The filament a tag describes: the catalog's own entry, or a private import."""
    from .spool_compat_catalog import _ensure_print_draft

    catalog = await match_catalog_filament(
        db, vendor_name=decoded.vendor_name, material=decoded.material, color_hex=decoded.color_hex
    )
    if catalog is not None:
        return await ensure_catalog_ref(db, kind="filament", catalog_id=catalog.id)
    # Rolls of one product share its GTIN, so a second roll reuses the first one's filament.
    external_id = f"gtin:{decoded.article_number}" if decoded.article_number else None
    if external_id is not None:
        existing = await db.scalar(
            select(SpoolCompatResource).where(
                SpoolCompatResource.kind == "filament",
                SpoolCompatResource.source_kind == "import",
                SpoolCompatResource.user_id == user_id,
                SpoolCompatResource.source_namespace == TAG_NAMESPACE,
                SpoolCompatResource.external_id == external_id,
            ).limit(1)
        )
        if existing is not None:
            return existing
    payload = {
        "name": decoded.name or decoded.material,
        "material": decoded.material,
        "density": decoded.density,
        "diameter": decoded.diameter,
        "weight": decoded.weight,
        "spool_weight": decoded.spool_weight,
        "color_hex": decoded.color_hex,
        "article_number": decoded.article_number,
        "settings_extruder_temp": decoded.extruder_temp,
        "settings_bed_temp": decoded.bed_temp,
    }
    if decoded.vendor_name:
        payload["vendor_id"] = await _import_vendor_wire_id(db, user_id, decoded.vendor_name)
    payload = {key: value for key, value in payload.items() if value is not None}
    ref = await create_import_ref(
        db, user_id=user_id, kind="filament", payload=payload,
        source_namespace=TAG_NAMESPACE, external_id=external_id,
    )
    await _ensure_print_draft(db, user_id=user_id, ref=ref, data=payload)
    return ref


async def create_spool_from_tag(
    db: AsyncSession, *, user_id: int, decoded: DecodedTag, uid: str, tag_format: str | None,
) -> bool:
    """Create a spool for an unknown tag from what the tag says, and link the tag to it.

    Only a filament tag that states its material and how much is left can
    become a spool: nothing is assumed in its place. Returns whether a spool
    was created.
    """
    initial = decoded.initial_weight or decoded.weight
    used = decoded.used_weight or 0.0
    if decoded.material_class != "FFF" or not decoded.material or not initial or used >= initial:
        return False
    try:
        ref = await _filament_ref_for_tag(db, user_id, decoded)
        spool = UserSpool(
            user_id=user_id,
            filament_id=ref.filament_id,
            compat_filament_ref_id=ref.id,
            empty_spool_weight_g=decoded.spool_weight,
            initial_weight_g=float(initial),
            used_weight_g=float(used),
            state=UserSpoolState.shelf,
            source="tag_scan",
            extra={},
        )
        db.add(spool)
        await db.flush()
        if used > 0:
            await record_spool_usage(
                db,
                spool=spool,
                event_type=PresetUsageEventType.reconcile_adjust,
                delta_weight_g=spool.used_weight_g,
                meta={
                    "reason": "opening_balance",
                    "balance_observed_at": datetime.now(timezone.utc).isoformat(),
                    "measured_remaining_g": spool.remaining_weight_g,
                },
            )
        await link_spool_tag(
            db, user_id=user_id, spool_id=spool.id, uid=uid, technology="nfc",
            tag_format=tag_format, source="tag_scan",
        )
        await db.commit()
    except (SpoolTagConflict, IntegrityError, ValueError):
        # Another scan of the same tag got there first, or the tag's values were refused.
        await db.rollback()
        logger.info("No spool was created from a scanned tag", exc_info=True)
        return False
    return True


async def _readers(db: AsyncSession, api_key: str | None) -> JSONResponse:
    from .spool_compat import _err, _resolve_user_and_device

    user, device = await _resolve_user_and_device(db, api_key)
    if user is None or device is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
    return JSONResponse(content=await list_readers(user.id))


@router.get("/v1/tag/reader")
@router.get("/api/v1/tag/reader")
async def tag_readers_with_header_key(
    db: Annotated[AsyncSession, Depends(get_db)],
    query_api_key: Annotated[str | None, Query(alias="api_key")] = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> JSONResponse:
    """List this account's tag readers that reported a scan recently."""
    return await _readers(db, query_api_key or header_api_key)


@router.get("/{api_key}/v1/tag/reader")
@router.get("/{api_key}/api/v1/tag/reader")
async def tag_readers(
    api_key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """List this account's tag readers that reported a scan recently."""
    return await _readers(db, api_key)


@router.websocket("/{api_key}/v1/tag/scan")
@router.websocket("/{api_key}/api/v1/tag/scan")
async def tag_scans_from_any_reader(websocket: WebSocket, api_key: str) -> None:
    from .spool_compat import serve_event_socket

    # A viewer of scans is not the printer link itself, so it holds no lease.
    await serve_event_socket(websocket, api_key, (TAG_SCAN_POOL,), holds_lease=False)


@router.websocket("/{api_key}/v1/tag/scan/{reader_id}")
@router.websocket("/{api_key}/api/v1/tag/scan/{reader_id}")
async def tag_scans_from_one_reader(websocket: WebSocket, api_key: str, reader_id: str) -> None:
    from .spool_compat import serve_event_socket

    await serve_event_socket(websocket, api_key, (TAG_SCAN_POOL, reader_id), holds_lease=False)


# Registered last in the compat router: the root socket's path is the bare
# versioned prefix, so every more specific socket must be matched before it.
@router.websocket("/{api_key}/v1/")
@router.websocket("/{api_key}/api/v1/")
async def all_changes(websocket: WebSocket, api_key: str) -> None:
    """Stream every spool, filament and vendor change of this account."""
    from .spool_compat import serve_event_socket

    await serve_event_socket(websocket, api_key, ALL_CHANGES_POOL)
