"""Native FilamentHub Bridge endpoints for OctoPrint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.octoprint_bridge import (
    OctoPrintBridgeHeartbeatRequest,
    OctoPrintBridgePairRequest,
    OctoPrintBridgePairResponse,
    OctoPrintBridgeStatusResponse,
    OctoPrintBridgeUsageRequest,
    OctoPrintBridgeUsageResponse,
    OctoPrintPairingCodeResponse,
)
from app.services.octoprint_bridge_service import (
    build_snapshot,
    get_bridge_status,
    issue_pairing_code,
    pair_bridge,
    record_heartbeat,
    record_usage_event,
    require_bridge_token,
    revoke_bridge,
)

router = APIRouter(prefix="/octoprint-bridge", tags=["octoprint-bridge"])


@router.post(
    "/connections/{physical_printer_id}/{material_system_id}/pairing-code",
    response_model=OctoPrintPairingCodeResponse,
)
async def create_pairing_code(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OctoPrintPairingCodeResponse:
    return await issue_pairing_code(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )


@router.get(
    "/connections/{physical_printer_id}/{material_system_id}",
    response_model=OctoPrintBridgeStatusResponse,
)
async def connection_status(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OctoPrintBridgeStatusResponse:
    return await get_bridge_status(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )


@router.delete(
    "/connections/{physical_printer_id}/{material_system_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_connection(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await revoke_bridge(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
    )


@router.post("/pair", response_model=OctoPrintBridgePairResponse)
@limiter.limit("10/minute")
async def pair(
    request: Request,
    payload: OctoPrintBridgePairRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OctoPrintBridgePairResponse:
    return await pair_bridge(db, payload)


@router.post("/heartbeat", response_model=OctoPrintBridgeStatusResponse)
async def heartbeat(
    payload: OctoPrintBridgeHeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeStatusResponse:
    context = await require_bridge_token(db, bridge_token)
    return await record_heartbeat(db, context, payload)


@router.get("/snapshot", response_model=None)
async def snapshot(
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    context = await require_bridge_token(db, bridge_token)
    result = await build_snapshot(db, context)
    etag = f'"{result.revision}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
        headers={"ETag": etag},
    )


@router.post("/usage", response_model=OctoPrintBridgeUsageResponse)
async def usage(
    payload: OctoPrintBridgeUsageRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeUsageResponse:
    context = await require_bridge_token(db, bridge_token)
    return await record_usage_event(db, context, payload)
