"""Provider-neutral local printer bridge endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_material_topology_report
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
    PrinterBridgeKlipperLinkRequest,
    PrinterBridgeKlipperLinkResponse,
    PrinterBridgePairingCodeResponse,
    PrinterBridgePairRequest,
    PrinterBridgePairResponse,
    PrinterBridgeSetupAttemptRequest,
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
    issue_moonraker_usage_bridge,
    issue_printer_bridge_pairing_code,
    pair_printer_bridge,
    record_printer_bridge_heartbeat,
    record_printer_bridge_setup_attempt,
    record_printer_bridge_usage_batch,
    require_printer_bridge_capability,
    require_printer_bridge_token,
    revoke_printer_bridge,
    revoke_printer_bridge_for_user,
    validate_snapshot_context,
)

router = APIRouter(prefix="/printer-bridge", tags=["printer-bridge"])


@router.get("/identity-context")
async def identity_context(
    db: Annotated[AsyncSession, Depends(get_db)],
    bridge_token: Annotated[str | None, Header(alias="X-FilamentHub-Bridge-Token")] = None,
) -> dict:
    from app.services.printer_identity_service import discovery_key
    context = await require_printer_bridge_token(db, bridge_token)
    return {"printer_discovery_key": await discovery_key(db, context.connector.user_id)}


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


@router.post("/setup-attempt", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def setup_attempt(
    request: Request,
    payload: PrinterBridgeSetupAttemptRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Record why a local setup with a pairing code ended without pairing.

    Always 204: the answer must not tell which pairing codes exist.
    """
    await record_printer_bridge_setup_attempt(db, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/klipper-usage-link", response_model=PrinterBridgeKlipperLinkResponse)
@limiter.limit("10/minute")
async def klipper_usage_link(
    request: Request,
    payload: PrinterBridgeKlipperLinkRequest,
    current_user: Annotated[User, Depends(require_material_topology_report)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterBridgeKlipperLinkResponse:
    """Let one OrcaSlicer installation report the filament a Klipper printer uses.

    A Klipper printer is not paired with a code: the plugin already reaches it
    through a connection bound to its card, and that binding is what is checked.
    """
    token, connector = await issue_moonraker_usage_bridge(
        db,
        user_id=current_user.id,
        physical_printer_id=payload.physical_printer_id,
        material_system_id=payload.material_system_id,
        source_instance_id=payload.source_instance_id,
        plugin_version=payload.plugin_version,
        capabilities=payload.capabilities,
    )
    return PrinterBridgeKlipperLinkResponse(
        bridge_token=token,
        physical_printer_id=connector.physical_printer_id,
        material_system_id=payload.material_system_id,
        provider=connector.provider,
    )


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
    if payload.slots:
        require_printer_bridge_capability(context.connector, "presence")
    if any(slot.spool_id is not None or slot.spool_identity_known for slot in payload.slots):
        require_printer_bridge_capability(context.connector, "spool_identity")
    if any(slot.tag_uid is not None for slot in payload.slots):
        require_printer_bridge_capability(context.connector, "tag_read")
    return await ingest_printer_bridge_snapshot(
        db,
        user_id=context.connector.user_id,
        physical_printer_id=context.connector.physical_printer_id,
        payload=payload,
        authenticated_connector_id=context.connector.id,
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
    require_printer_bridge_capability(context.connector, "read")
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
