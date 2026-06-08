"""Endpoints for OrcaSlicer preset-slot synchronisation (HH integration)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import ERR_DEVICE_NOT_FOUND, raise_error
from app.db.session import get_db
from app.models.preset_gate_state import PresetGateStateSource
from app.models.user import User
from app.schemas.preset_slot_sync import (
    GateStateResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    HHSnapshotRequest,
    HHSnapshotResponse,
    ManualAssignmentRequest,
    ManualAssignmentResponse,
    SlotStateResponse,
    UsageEstimateRequest,
    UsageEstimateResponse,
)
from app.services.preset_slot_sync_service import (
    get_device_by_fingerprint,
    get_gate_states,
    handle_heartbeat,
    handle_hh_snapshot,
    handle_manual_assignment,
    handle_usage_estimate,
)

router = APIRouter(
    prefix="/orcaslicer/preset-slot-sync",
    tags=["orca-preset-slot-sync"],
)


@router.post("/device/heartbeat", response_model=HeartbeatResponse)
async def device_heartbeat(
    payload: HeartbeatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HeartbeatResponse:
    """Register or update device presence. Called on Orca startup / printer connect."""
    device = await handle_heartbeat(
        db,
        current_user,
        fingerprint=payload.device_fingerprint,
        device_name=payload.device_name,
        supports_hh=payload.supports_hh,
        gate_count=payload.gate_count,
    )
    return HeartbeatResponse(device_id=device.id)


@router.post("/hh/snapshot", response_model=HHSnapshotResponse)
async def hh_snapshot(
    payload: HHSnapshotRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> HHSnapshotResponse:
    """Upload a Happy Hare gate snapshot from OrcaSlicer."""
    device, updated, mismatches = await handle_hh_snapshot(db, current_user, payload)
    return HHSnapshotResponse(
        device_id=device.id,
        updated_gates=updated,
        mismatches=mismatches,
    )


@router.post("/manual/assignment", response_model=ManualAssignmentResponse)
async def manual_assignment(
    payload: ManualAssignmentRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManualAssignmentResponse:
    """Manually assign a preset to a gate from OrcaSlicer."""
    state = await handle_manual_assignment(
        db, current_user, payload, PresetGateStateSource.manual_orca
    )
    return ManualAssignmentResponse(gate_state_id=state.id)


@router.post("/usage/estimate", response_model=UsageEstimateResponse)
async def usage_estimate(
    payload: UsageEstimateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UsageEstimateResponse:
    """Submit filament usage estimate after a print job."""
    event = await handle_usage_estimate(db, current_user, payload)
    return UsageEstimateResponse(event_id=event.id)


@router.get("/state", response_model=SlotStateResponse)
async def get_slot_state(
    device_fingerprint: Annotated[str, Query(max_length=200)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SlotStateResponse:
    """Get current slot map for a device (called by Orca on open/refresh)."""
    device = await get_device_by_fingerprint(db, current_user.id, device_fingerprint)
    if device is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)

    states = await get_gate_states(db, device.id)
    return SlotStateResponse(
        device_id=device.id,
        device_fingerprint=device.device_fingerprint,
        gate_count=device.gate_count,
        gates=[GateStateResponse.model_validate(s) for s in states],
    )
