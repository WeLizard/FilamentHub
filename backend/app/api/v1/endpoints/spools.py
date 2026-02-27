"""Endpoints for user spool (filament inventory) management."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.spool import SpoolCreateRequest, SpoolResponse, SpoolUpdateRequest, SpoolUseRequest
from app.services.spool_service import (
    create_spool,
    delete_spool,
    list_spools,
    update_spool,
    use_spool,
)

router = APIRouter(prefix="/spools", tags=["spools"])


@router.get("", response_model=list[SpoolResponse])
async def get_spools(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SpoolResponse]:
    """List all spools for the current user."""
    return await list_spools(db, current_user.id)


@router.post("", response_model=SpoolResponse, status_code=status.HTTP_201_CREATED)
async def add_spool(
    payload: SpoolCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolResponse:
    """Add a new spool to the user's inventory."""
    return await create_spool(db, current_user, payload)


@router.patch("/{spool_id}", response_model=SpoolResponse)
async def edit_spool(
    spool_id: int,
    payload: SpoolUpdateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolResponse:
    """Update spool details."""
    return await update_spool(db, current_user, spool_id, payload)


@router.post("/{spool_id}/use", response_model=SpoolResponse)
async def record_usage(
    spool_id: int,
    payload: SpoolUseRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolResponse:
    """Record filament consumption from a spool."""
    return await use_spool(db, current_user, spool_id, payload.delta_weight_g)


@router.delete("/{spool_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_spool(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a spool from inventory."""
    await delete_spool(db, current_user, spool_id)
