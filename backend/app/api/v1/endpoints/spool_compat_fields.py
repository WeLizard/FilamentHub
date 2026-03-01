"""Extra fields API for Spoolman compatibility."""

from __future__ import annotations

from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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


_extra_fields_cache: dict[str, list[dict]] = {}


def _get_entity_fields(entity_type: EntityType) -> list[dict]:
    return list(_extra_fields_cache.get(entity_type.value, []))


def _set_entity_fields(entity_type: EntityType, fields: list[dict]) -> list[dict]:
    _extra_fields_cache[entity_type.value] = fields
    return fields


@router.get("/v1/field/{entity_type}")
@router.get("/{api_key}/v1/field/{entity_type}")
@router.get("/{api_key}/api/v1/field/{entity_type}")
async def get_fields(entity_type: EntityType, api_key: str | None = None) -> list[dict]:
    _ = api_key
    return _get_entity_fields(entity_type)


@router.post("/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/api/v1/field/{entity_type}/{key}")
async def add_or_update_field(
    entity_type: EntityType,
    key: str,
    body: ExtraFieldParams,
    api_key: str | None = None,
) -> list[dict]:
    _ = api_key
    fields = [item for item in _get_entity_fields(entity_type) if item.get("key") != key]
    field = ExtraFieldResponse(key=key, entity_type=entity_type, **body.model_dump()).model_dump()
    fields.append(field)
    return _set_entity_fields(entity_type, fields)


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
async def delete_field(entity_type: EntityType, key: str, api_key: str | None = None) -> list[dict]:
    _ = api_key
    fields = _get_entity_fields(entity_type)
    next_fields = [item for item in fields if item.get("key") != key]
    if len(next_fields) == len(fields):
        raise HTTPException(
            status_code=404,
            detail=f"Extra field '{key}' not found for {entity_type.value}",
        )
    return _set_entity_fields(entity_type, next_fields)
