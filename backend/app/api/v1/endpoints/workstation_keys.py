"""Manage the long-lived keys a desktop plugin keeps for background reporting."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.services.workstation_key_service import (
    issue_workstation_key,
    list_workstation_keys,
    revoke_workstation_key,
)

router = APIRouter(prefix="/workstation-keys", tags=["workstation-keys"])


class WorkstationKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    model_config = {"str_strip_whitespace": True}


class WorkstationKeyResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class WorkstationKeyIssued(WorkstationKeyResponse):
    key: str


@router.get("", response_model=list[WorkstationKeyResponse])
async def list_keys(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkstationKeyResponse]:
    return [
        WorkstationKeyResponse.model_validate(row)
        for row in await list_workstation_keys(db, current_user.id)
    ]


@router.post("", response_model=WorkstationKeyIssued, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: WorkstationKeyCreate,
    response: Response,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkstationKeyIssued:
    row, key = await issue_workstation_key(db, current_user, payload.name)
    response.headers["Cache-Control"] = "no-store"
    return WorkstationKeyIssued(
        id=row.id, name=row.name, created_at=row.created_at, last_used_at=None, key=key
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_key(
    key_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await revoke_workstation_key(db, current_user.id, key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
