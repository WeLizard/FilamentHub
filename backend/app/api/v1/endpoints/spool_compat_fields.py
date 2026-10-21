"""Extra fields API for Spoolman compatibility."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status
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


_BUILTIN_FIELDS: dict[EntityType, list[dict]] = {
    EntityType.spool: [
        {
            "key": "rfid_tag",
            "entity_type": EntityType.spool.value,
            "name": "RFID",
            "field_type": ExtraFieldType.text.value,
            "default_value": '""',
            "choices": None,
            "multi_choice": None,
            "order": 0,
            "unit": None,
        }
    ]
}


async def _get_entity_fields(
    db: AsyncSession, user_id: int, entity_type: EntityType
) -> list[dict]:
    from app.services.spool_compat_resource_service import list_field_defs

    builtins = list(_BUILTIN_FIELDS.get(entity_type, []))
    builtin_keys = {field["key"] for field in builtins}
    custom = [
        field
        for field in await list_field_defs(db, user_id=user_id, kind=entity_type.value)
        if field.get("key") not in builtin_keys
    ]
    return builtins + custom


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
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> list[dict]:
    user_id = await _resolve_user_id(db, api_key or header_api_key)
    if user_id is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    return await _get_entity_fields(db, user_id, entity_type)


@router.post("/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/v1/field/{entity_type}/{key}")
@router.post("/{api_key}/api/v1/field/{entity_type}/{key}")
async def add_or_update_field(
    entity_type: EntityType,
    key: Annotated[str, Path(min_length=1, max_length=64, pattern="^[a-z0-9_]+$")],
    body: ExtraFieldParams,
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: str | None = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> list[dict]:
    from app.services.spool_compat_resource_service import upsert_field_def

    user_id = await _resolve_user_id(db, api_key or header_api_key)
    if user_id is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    builtin = next(
        (field for field in _BUILTIN_FIELDS.get(entity_type, []) if field["key"] == key),
        None,
    )
    if builtin is not None:
        if body.field_type.value != builtin["field_type"]:
            raise HTTPException(status_code=400, detail="The RFID field must remain a text field.")
    else:
        field = ExtraFieldResponse(
            key=key, entity_type=entity_type, **body.model_dump()
        ).model_dump(mode="json")
        await upsert_field_def(
            db, user_id=user_id, kind=entity_type.value, key=key, definition=field
        )
        await db.commit()
    return await _get_entity_fields(db, user_id, entity_type)


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
    key: Annotated[str, Path(min_length=1, max_length=64, pattern="^[a-z0-9_]+$")],
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: str | None = None,
    header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> list[dict]:
    from app.services.spool_compat_resource_service import (
        CompatFieldProtected,
        delete_field_def,
    )

    user_id = await _resolve_user_id(db, api_key or header_api_key)
    if user_id is None:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_INVALID_API_KEY)
    if any(field["key"] == key for field in _BUILTIN_FIELDS.get(entity_type, [])):
        raise HTTPException(status_code=409, detail="The RFID binding field cannot be deleted.")
    try:
        deleted = await delete_field_def(
            db, user_id=user_id, kind=entity_type.value, key=key
        )
    except CompatFieldProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Extra field '{key}' not found for {entity_type.value}",
        )
    await db.commit()
    return await _get_entity_fields(db, user_id, entity_type)
