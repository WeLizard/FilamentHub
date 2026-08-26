"""Native FilamentHub Bridge endpoints for OctoPrint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.limiter import adapter_token_key, client_key, limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.octoprint_bridge import (
    OctoPrintBridgeHeartbeatRequest,
    OctoPrintBridgePairRequest,
    OctoPrintBridgePairResponse,
    OctoPrintBridgeRoutingState,
    OctoPrintBridgeRoutingUpdateRequest,
    OctoPrintBridgeSnapshotResponse,
    OctoPrintBridgeSpoolAssignmentRequest,
    OctoPrintBridgeSpoolOptionsResponse,
    OctoPrintBridgeStatusResponse,
    OctoPrintBridgeUsageRequest,
    OctoPrintBridgeUsageResponse,
    OctoPrintPairingCodeResponse,
)
from app.services.octoprint_bridge_service import (
    build_snapshot,
    get_bridge_status,
    issue_pairing_code,
    list_bridge_spool_options,
    pair_bridge,
    record_heartbeat,
    record_usage_event,
    require_bridge_token,
    revoke_bridge,
    revoke_bridge_context,
    update_bridge_routing_configuration,
    update_bridge_spool_assignment,
    update_user_routing_configuration,
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


@router.put(
    "/connections/{physical_printer_id}/{material_system_id}/routing",
    response_model=OctoPrintBridgeRoutingState,
)
async def update_connection_routing(
    physical_printer_id: int,
    material_system_id: int,
    payload: OctoPrintBridgeRoutingUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OctoPrintBridgeRoutingState:
    return await update_user_routing_configuration(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        payload=payload,
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


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute", key_func=adapter_token_key)
async def revoke_current_connection(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> None:
    context = await require_bridge_token(db, bridge_token)
    await revoke_bridge_context(db, context)


@router.post("/pair", response_model=OctoPrintBridgePairResponse)
@limiter.limit("10/minute")
async def pair(
    request: Request,
    payload: OctoPrintBridgePairRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OctoPrintBridgePairResponse:
    return await pair_bridge(db, payload)


@router.post("/heartbeat", response_model=OctoPrintBridgeStatusResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def heartbeat(
    request: Request,
    payload: OctoPrintBridgeHeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeStatusResponse:
    context = await require_bridge_token(db, bridge_token)
    return await record_heartbeat(db, context, payload)


@router.put("/routing", response_model=OctoPrintBridgeRoutingState)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def update_current_routing(
    request: Request,
    payload: OctoPrintBridgeRoutingUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeRoutingState:
    context = await require_bridge_token(db, bridge_token)
    return await update_bridge_routing_configuration(
        db,
        context=context,
        payload=payload,
    )


@router.get("/snapshot", response_model=None)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def snapshot(
    request: Request,
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


@router.get("/spools", response_model=OctoPrintBridgeSpoolOptionsResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("60/minute", key_func=adapter_token_key)
async def spool_options(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
    query: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OctoPrintBridgeSpoolOptionsResponse:
    context = await require_bridge_token(db, bridge_token)
    return await list_bridge_spool_options(
        db,
        context,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/material-slots/{material_slot_id}",
    response_model=OctoPrintBridgeSnapshotResponse,
)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def update_spool_assignment(
    material_slot_id: int,
    request: Request,
    payload: OctoPrintBridgeSpoolAssignmentRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeSnapshotResponse:
    context = await require_bridge_token(db, bridge_token)
    return await update_bridge_spool_assignment(
        db,
        context,
        material_slot_id=material_slot_id,
        payload=payload,
    )


@router.post("/usage", response_model=OctoPrintBridgeUsageResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("120/minute", key_func=adapter_token_key)
async def usage(
    request: Request,
    payload: OctoPrintBridgeUsageRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> OctoPrintBridgeUsageResponse:
    context = await require_bridge_token(db, bridge_token)
    return await record_usage_event(db, context, payload)
