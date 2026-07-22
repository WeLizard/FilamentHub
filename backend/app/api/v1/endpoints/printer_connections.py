"""OrcaSlicer plugin printer-connection observation endpoint (stage A)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_user_or_plugin_preset_write
from app.db.session import get_db
from app.models.user import User
from app.schemas.printer_connection_observation import (
    PrinterConnectionBindingResponse,
    PrinterConnectionObserveRequest,
    PrinterConnectionObserveResponse,
)
from app.services.physical_printer_discovery_service import (
    display_endpoint,
    list_user_bindings,
    reconcile_user_printers,
)
from app.services.printer_connection_observation_service import record_observations

router = APIRouter(prefix="/orcaslicer/printer-connections", tags=["printer-connections"])


@router.post("/observe", response_model=PrinterConnectionObserveResponse)
async def observe_printer_connections(
    payload: PrinterConnectionObserveRequest,
    current_user: Annotated[User, Depends(get_current_user_or_plugin_preset_write)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterConnectionObserveResponse:
    """Record observed printer connection data from the OrcaSlicer plugin, then
    reconcile it into physical printers + connection bindings."""
    accepted, matched, unmatched = await record_observations(
        db, current_user.id, payload.source_instance_id, payload.observations
    )
    await reconcile_user_printers(db, current_user.id)
    return PrinterConnectionObserveResponse(
        accepted=accepted, matched=matched, unmatched=unmatched
    )


@router.get("/bindings", response_model=list[PrinterConnectionBindingResponse])
async def list_connection_bindings(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PrinterConnectionBindingResponse]:
    """Safe display view of the user's connection bindings (endpoint as a label)."""
    bindings = await list_user_bindings(db, current_user.id)
    return [
        PrinterConnectionBindingResponse(
            physical_printer_id=b.physical_printer_id,
            provider=b.provider,
            display_endpoint=display_endpoint(b),
            last_seen_at=b.last_seen_at,
        )
        for b in bindings
    ]
