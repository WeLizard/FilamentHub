"""Provider-neutral local printer bridge endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.limiter import adapter_token_key, client_key, limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.material_contract import (
    PrinterBridgeSnapshotRequest,
    PrinterBridgeSnapshotResponse,
)
from app.schemas.printer_bridge import (
    PrinterBridgeDesiredSnapshotResponse,
    PrinterBridgeHeartbeatRequest,
    PrinterBridgeHeartbeatResponse,
    PrinterBridgePairingCodeResponse,
    PrinterBridgePairRequest,
    PrinterBridgePairResponse,
    PrinterBridgeStatusResponse,
    PrinterBridgeTransport,
    PrinterBridgeUsageBatchRequest,
    PrinterBridgeUsageBatchResponse,
)
from app.services.material_contract_service import (
    build_printer_bridge_desired_snapshot,
    ingest_printer_bridge_snapshot,
)
from app.services.printer_bridge_service import (
    get_printer_bridge_status,
    issue_printer_bridge_pairing_code,
    pair_printer_bridge,
    record_printer_bridge_heartbeat,
    record_printer_bridge_usage_batch,
    require_printer_bridge_token,
    revoke_printer_bridge,
    revoke_printer_bridge_for_user,
    validate_snapshot_context,
)

router = APIRouter(prefix="/printer-bridge", tags=["printer-bridge"])


@router.post(
    "/connections/{physical_printer_id}/{material_system_id}/pairing-code",
    response_model=PrinterBridgePairingCodeResponse,
)
async def create_pairing_code(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    transport: Annotated[PrinterBridgeTransport, Query()] = "orca_plugin_lan",
) -> PrinterBridgePairingCodeResponse:
    return await issue_printer_bridge_pairing_code(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        transport=transport,
    )


@router.get(
    "/connections/{physical_printer_id}/{material_system_id}",
    response_model=PrinterBridgeStatusResponse,
)
async def connection_status(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    transport: Annotated[PrinterBridgeTransport, Query()] = "orca_plugin_lan",
) -> PrinterBridgeStatusResponse:
    return await get_printer_bridge_status(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        transport=transport,
    )


@router.delete(
    "/connections/{physical_printer_id}/{material_system_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_owned_connection(
    physical_printer_id: int,
    material_system_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    transport: Annotated[PrinterBridgeTransport, Query()] = "orca_plugin_lan",
) -> None:
    await revoke_printer_bridge_for_user(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
        transport=transport,
    )


@router.post("/pair", response_model=PrinterBridgePairResponse)
@limiter.limit("10/minute")
async def pair(
    request: Request,
    payload: PrinterBridgePairRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterBridgePairResponse:
    return await pair_printer_bridge(db, payload)


@router.post("/snapshot", response_model=PrinterBridgeSnapshotResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def observed_snapshot(
    request: Request,
    payload: PrinterBridgeSnapshotRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> PrinterBridgeSnapshotResponse:
    context = await require_printer_bridge_token(db, bridge_token)
    validate_snapshot_context(
        context,
        material_system_id=payload.material_system_id,
        source_instance_id=payload.source_instance_id,
        provider=payload.provider,
        transport=payload.transport,
    )
    return await ingest_printer_bridge_snapshot(
        db,
        user_id=context.connector.user_id,
        physical_printer_id=context.connector.physical_printer_id,
        payload=payload,
    )


@router.get("/snapshot", response_model=None)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def desired_snapshot(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    context = await require_printer_bridge_token(db, bridge_token)
    result: PrinterBridgeDesiredSnapshotResponse = await build_printer_bridge_desired_snapshot(
        db,
        context.connector,
    )
    etag = f'"{result.revision}"'
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        content=result.model_dump_json(),
        media_type="application/json",
        headers={"ETag": etag},
    )


@router.post("/heartbeat", response_model=PrinterBridgeHeartbeatResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("30/minute", key_func=adapter_token_key)
async def heartbeat(
    request: Request,
    payload: PrinterBridgeHeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> PrinterBridgeHeartbeatResponse:
    context = await require_printer_bridge_token(db, bridge_token)
    return await record_printer_bridge_heartbeat(db, context, payload)


@router.post("/usage-batches", response_model=PrinterBridgeUsageBatchResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("120/minute", key_func=adapter_token_key)
async def usage_batch(
    request: Request,
    payload: PrinterBridgeUsageBatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> PrinterBridgeUsageBatchResponse:
    context = await require_printer_bridge_token(db, bridge_token)
    validate_snapshot_context(
        context,
        material_system_id=payload.material_system_id,
        source_instance_id=payload.source_instance_id,
        provider=payload.provider,
        transport=payload.transport,
    )
    return await record_printer_bridge_usage_batch(db, context, payload)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_connection(
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[
        str | None,
        Header(alias="X-FilamentHub-Bridge-Token"),
    ] = None,
) -> None:
    context = await require_printer_bridge_token(db, bridge_token)
    await revoke_printer_bridge(db, context)
