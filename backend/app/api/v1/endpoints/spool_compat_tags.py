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

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, WebSocket, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.tag_scan_relay import list_readers

from .spool_compat_ws import ALL_CHANGES_POOL, TAG_SCAN_POOL

router = APIRouter(tags=["spool_compat"])


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
