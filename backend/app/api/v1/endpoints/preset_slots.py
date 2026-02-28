"""Endpoints for web-side preset slot management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.preset_slot_sync import GateStateResponse, PresetSlotAssignRequest
from app.services.preset_slot_sync_service import (
    clear_device_slots,
    get_gate_states,
    require_device,
    web_assign_preset_to_slot,
)

router = APIRouter(prefix="/preset-slots", tags=["preset-slots"])


@router.get("", response_model=list[GateStateResponse])
async def list_preset_slots(
    device_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GateStateResponse]:
    """Get the current gate/slot map for a device."""
    device = await require_device(db, current_user.id, device_id)
    states = await get_gate_states(db, device.id)
    return [GateStateResponse.model_validate(s) for s in states]


@router.patch("/{device_id}/{gate_index}", response_model=GateStateResponse)
async def assign_preset_to_slot(
    device_id: int,
    gate_index: int,
    payload: PresetSlotAssignRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GateStateResponse:
    """Assign (or clear) a preset on a specific gate (web manual source)."""
    preset_id_provided = "preset_id" in payload.model_fields_set
    spool_id_provided = "spool_id" in payload.model_fields_set
    state = await web_assign_preset_to_slot(
        db,
        current_user,
        device_id=device_id,
        gate_index=gate_index,
        preset_id=payload.preset_id,
        spool_id=payload.spool_id,
        preset_id_provided=preset_id_provided,
        spool_id_provided=spool_id_provided,
    )
    return GateStateResponse.model_validate(state)


@router.post("/{device_id}/clear")
async def clear_slots(
    device_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Clear all preset assignments on a device's gates."""
    cleared = await clear_device_slots(db, current_user, device_id)
    return {"cleared": cleared}
