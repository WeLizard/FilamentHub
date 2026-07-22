"""OrcaSlicer plugin printer-connection observation endpoint (stage A)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_or_plugin_preset_write
from app.db.session import get_db
from app.models.user import User
from app.schemas.printer_connection_observation import (
    PrinterConnectionObserveRequest,
    PrinterConnectionObserveResponse,
)
from app.services.printer_connection_observation_service import record_observations

router = APIRouter(prefix="/orcaslicer/printer-connections", tags=["printer-connections"])


@router.post("/observe", response_model=PrinterConnectionObserveResponse)
async def observe_printer_connections(
    payload: PrinterConnectionObserveRequest,
    current_user: Annotated[User, Depends(get_current_user_or_plugin_preset_write)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterConnectionObserveResponse:
    """Record observed printer connection data from the OrcaSlicer plugin.

    Staging/evidence only — no PhysicalPrinter or ConnectionBinding is created.
    """
    accepted, matched, unmatched = await record_observations(
        db, current_user.id, payload.source_instance_id, payload.observations
    )
    return PrinterConnectionObserveResponse(
        accepted=accepted, matched=matched, unmatched=unmatched
    )
