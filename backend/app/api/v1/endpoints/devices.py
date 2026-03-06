"""Endpoints for user printer device management."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.security import generate_api_key
from app.db.session import get_db
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.preset_slot_sync import (
    DeviceCreateWithKeyRequest,
    DeviceCreateWithKeyResponse,
    DeviceRegenerateKeyResponse,
    DeviceRegisterRequest,
    DeviceResponse,
    DeviceStateResponse,
    DeviceUpdateRequest,
    GateStateResponse,
)
from app.services.preset_slot_sync_service import (
    get_gate_states,
    list_user_devices,
    register_or_update_device,
    require_device,
    update_device,
)

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceResponse])
async def list_devices(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeviceResponse]:
    """List all printer devices registered by the current user."""
    devices = await list_user_devices(db, current_user.id)
    return [DeviceResponse.model_validate(d) for d in devices]


@router.post("/register-or-update", response_model=DeviceResponse)
async def register_or_update(
    payload: DeviceRegisterRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceResponse:
    """Register a new device or update an existing one by fingerprint."""
    device = await register_or_update_device(db, current_user, payload)
    return DeviceResponse.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceResponse)
async def patch_device(
    device_id: int,
    payload: DeviceUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceResponse:
    """Update device settings (name, gate_count, supports_hh)."""
    device = await update_device(db, current_user.id, device_id, payload)
    return DeviceResponse.model_validate(device)


@router.get("/{device_id}/state", response_model=DeviceStateResponse)
async def get_device_state(
    device_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceStateResponse:
    """Get a device with its current gate states."""
    device = await require_device(db, current_user.id, device_id)
    gate_states = await get_gate_states(db, device.id)
    return DeviceStateResponse(
        device=DeviceResponse.model_validate(device),
        gates=[GateStateResponse.model_validate(g) for g in gate_states],
    )


@router.post("/create-with-key", response_model=DeviceCreateWithKeyResponse)
async def create_device_with_key(
    payload: DeviceCreateWithKeyRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceCreateWithKeyResponse:
    """Create a new printer device and generate an API key for it."""
    new_key = generate_api_key()
    fingerprint = f"manual-{uuid.uuid4().hex[:12]}"
    device = UserPrinterDevice(
        user_id=current_user.id,
        name=payload.name.strip(),
        device_fingerprint=fingerprint,
        api_key=new_key,
        supports_hh=True,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceCreateWithKeyResponse(
        device=DeviceResponse.model_validate(device),
        api_key=new_key,
    )


@router.post("/{device_id}/regenerate-key", response_model=DeviceRegenerateKeyResponse)
async def regenerate_device_key(
    device_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DeviceRegenerateKeyResponse:
    """Regenerate the API key for a device. The old key stops working immediately."""
    device = await require_device(db, current_user.id, device_id)
    new_key = generate_api_key()
    device.api_key = new_key
    await db.commit()
    return DeviceRegenerateKeyResponse(api_key=new_key)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_device(
    device_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a printer device and all its gate states."""
    device = await require_device(db, current_user.id, device_id)
    await db.delete(device)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
