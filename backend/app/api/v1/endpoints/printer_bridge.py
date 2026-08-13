"""Provider-neutral local printer bridge endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.material_contract import (
    PrinterBridgeSnapshotRequest,
    PrinterBridgeSnapshotResponse,
)
from app.schemas.printer_bridge import (
    PrinterBridgePairingCodeResponse,
    PrinterBridgePairRequest,
    PrinterBridgePairResponse,
    PrinterBridgeStatusResponse,
)
from app.services.material_contract_service import ingest_printer_bridge_snapshot
from app.services.printer_bridge_service import (
    get_printer_bridge_status,
    issue_printer_bridge_pairing_code,
    pair_printer_bridge,
    require_printer_bridge_token,
    revoke_printer_bridge,
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
) -> PrinterBridgePairingCodeResponse:
    return await issue_printer_bridge_pairing_code(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
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
) -> PrinterBridgeStatusResponse:
    return await get_printer_bridge_status(
        db,
        user_id=current_user.id,
        physical_printer_id=physical_printer_id,
        material_system_id=material_system_id,
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
async def snapshot(
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
    )
    return await ingest_printer_bridge_snapshot(
        db,
        user_id=context.connector.user_id,
        physical_printer_id=context.connector.physical_printer_id,
        payload=payload,
    )


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
