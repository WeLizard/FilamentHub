"""Extra fields API for Spoolman compatibility."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_INVALID_API_KEY, raise_error
from app.db.session import get_db

router = APIRouter()


class EntityType(str, Enum):
    vendor = "vendor"
    filament = "filament"
    spool = "spool"


class ExtraFieldType(str, Enum):
    text = "text"
    integer = "integer"
    integer_range = "integer_range"
    float_ = "float"
    float_range = "float_range"
    datetime = "datetime"
    boolean = "boolean"
    choice = "choice"


class ExtraFieldParams(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    field_type: ExtraFieldType
    default_value: str | None = None
    choices: list[str] | None = None
    multi_choice: bool | None = None
    order: int = 0
    unit: str | None = Field(default=None, max_length=16)


class ExtraFieldResponse(ExtraFieldParams):
    key: str
    entity_type: EntityType


_extra_fields_cache: dict[tuple[int, str], list[dict]] = {}


def _get_entity_fields(user_id: int, entity_type: EntityType) -> list[dict]:
    return list(_extra_fields_cache.get((user_id, entity_type.value), []))


def _set_entity_fields(user_id: int, entity_type: EntityType, fields: list[dict]) -> list[dict]:
    _extra_fields_cache[(user_id, entity_type.value)] = fields
    return fields


async def _resolve_user_id(db: AsyncSession, api_key: str | None) -> int | None:
    """Resolve the Spoolman-compat per-device api_key to an active user id."""
    from .spool_compat import _resolve_user_and_device  # lazy: avoids circular import

    user, _device = await _resolve_user_and_device(db, api_key)
    return user.id if user is not None else None


@router.get("/v1/field/{entity_type}")
@router.get("/{api_key}/v1/field/{entity_type}")
@router.get("/{api_key}/api/v1/field/{entity_type}")
async def get_fields(
    entity_type: EntityType,
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: str | None = None,
) -> list[dict]:
    user_id = await _resolve_user_id(db, api_key)
    if user_id is None:
        return []
    return _get_entity_fields(user_id, entity_type)


@router.post("/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/api/v1/field/{entity_type}/{key}")
async def add_or_update_field(
    entity_type: EntityType,
    key: str,
    body: ExtraFieldParams,
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: str | None = None,
) -> list[dict]:
    user_id = await _resolve_user_id(db, api_key)
    if user_id is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    fields = [item for item in _get_entity_fields(user_id, entity_type) if item.get("key") != key]
    field = ExtraFieldResponse(key=key, entity_type=entity_type, **body.model_dump()).model_dump()
    fields.append(field)
    return _set_entity_fields(user_id, entity_type, fields)


@router.delete(
    "/v1/field/{entity_type}/{key}",
    response_model=list[dict],
    responses={404: {"description": "Not found"}},
)
@router.delete(
    "/{api_key}/v1/field/{entity_type}/{key}",
    response_model=list[dict],
    responses={404: {"description": "Not found"}},
)
@router.delete(
    "/{api_key}/api/v1/field/{entity_type}/{key}",
    response_model=list[dict],
    responses={404: {"description": "Not found"}},
)
async def delete_field(
    entity_type: EntityType,
    key: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: str | None = None,
) -> list[dict]:
    user_id = await _resolve_user_id(db, api_key)
    if user_id is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    fields = _get_entity_fields(user_id, entity_type)
    next_fields = [item for item in fields if item.get("key") != key]
    if len(next_fields) == len(fields):
        raise HTTPException(
            status_code=404,
            detail=f"Extra field '{key}' not found for {entity_type.value}",
        )
    return _set_entity_fields(user_id, entity_type, next_fields)
