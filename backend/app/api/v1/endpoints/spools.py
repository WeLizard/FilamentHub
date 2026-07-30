"""Endpoints for user spool (filament inventory) management."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.spool import (
    SpoolCreateRequest,
    SpoolImportColumnMapping,
    SpoolImportPreviewResponse,
    SpoolImportResponse,
    SpoolManagerImportResponse,
    SpoolManagerPreviewResponse,
    SpoolResponse,
    SpoolUpdateRequest,
    SpoolUsageEventResponse,
    SpoolUseRequest,
)
from app.core.errors import (
    ERR_SPOOL_IMPORT_FILE_TOO_LARGE,
    ERR_SPOOL_IMPORT_INVALID_CSV,
    raise_error,
)
from app.services.spool_service import (
    create_spool,
    delete_spool,
    list_spools,
    update_spool,
    use_spool,
)
from app.services.spool_usage_service import list_spool_usage, revert_spool_usage
from app.services.spoolmanager_import_service import (
    import_spoolmanager_csv,
    preview_spoolmanager_import,
)
from app.services.spool_import_service import import_spool_file, preview_spool_import

router = APIRouter(prefix="/spools", tags=["spools"])
MAX_SPOOLMANAGER_CSV_BYTES = 2 * 1024 * 1024


async def _read_spoolmanager_csv(file: UploadFile) -> bytes:
    data = await file.read(MAX_SPOOLMANAGER_CSV_BYTES + 1)
    if len(data) > MAX_SPOOLMANAGER_CSV_BYTES:
        raise_error(413, ERR_SPOOL_IMPORT_FILE_TOO_LARGE)
    return data


def _parse_import_mapping(value: str | None) -> SpoolImportColumnMapping | None:
    if value is None or not value.strip():
        return None
    try:
        return SpoolImportColumnMapping.model_validate_json(value)
    except ValidationError:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)


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


@router.post("/import/preview", response_model=SpoolImportPreviewResponse)
async def preview_import_file(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mapping: Annotated[str | None, Form()] = None,
) -> SpoolImportPreviewResponse:
    """Detect a supported spool export or prepare a safe manual CSV mapping."""
    data = await _read_spoolmanager_csv(file)
    return await preview_spool_import(
        db,
        user_id=current_user.id,
        file_name=file.filename or "spools.csv",
        data=data,
        mapping=_parse_import_mapping(mapping),
    )


@router.post(
    "/import",
    response_model=SpoolImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_file(
    file: Annotated[UploadFile, File(...)],
    selected_fingerprints: Annotated[str, Form(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    mapping: Annotated[str | None, Form()] = None,
) -> SpoolImportResponse:
    """Import selected rows after source detection or user-confirmed mapping."""
    try:
        selected = json.loads(selected_fingerprints)
    except json.JSONDecodeError:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
    if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
    data = await _read_spoolmanager_csv(file)
    return await import_spool_file(
        db,
        user=current_user,
        file_name=file.filename or "spools.csv",
        data=data,
        selected_fingerprints=set(selected),
        mapping=_parse_import_mapping(mapping),
    )


@router.post(
    "/import/spoolmanager/preview",
    response_model=SpoolManagerPreviewResponse,
)
async def preview_spoolmanager_csv(
    file: Annotated[UploadFile, File(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolManagerPreviewResponse:
    """Validate a SpoolManager CSV and show conservative catalog matches."""
    data = await _read_spoolmanager_csv(file)
    return await preview_spoolmanager_import(
        db,
        user_id=current_user.id,
        file_name=file.filename or "spools.csv",
        data=data,
    )


@router.post(
    "/import/spoolmanager",
    response_model=SpoolManagerImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_spoolmanager_file(
    file: Annotated[UploadFile, File(...)],
    selected_fingerprints: Annotated[str, Form(...)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolManagerImportResponse:
    """Import explicitly selected rows from a previously previewed CSV."""
    try:
        selected = json.loads(selected_fingerprints)
    except json.JSONDecodeError:
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
    if not isinstance(selected, list) or not all(isinstance(item, str) for item in selected):
        raise_error(400, ERR_SPOOL_IMPORT_INVALID_CSV)
    data = await _read_spoolmanager_csv(file)
    return await import_spoolmanager_csv(
        db,
        user=current_user,
        file_name=file.filename or "spools.csv",
        data=data,
        selected_fingerprints=set(selected),
    )


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


@router.get("/{spool_id}/usage", response_model=list[SpoolUsageEventResponse])
async def get_spool_usage(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SpoolUsageEventResponse]:
    """Consumption history of one spool."""
    return await list_spool_usage(db, user_id=current_user.id, spool_id=spool_id)


@router.post("/{spool_id}/usage/{event_id}/revert", response_model=SpoolUsageEventResponse)
async def revert_spool_usage_event(
    spool_id: int,
    event_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolUsageEventResponse:
    """Give back what one consumption record took."""
    return await revert_spool_usage(
        db, user_id=current_user.id, spool_id=spool_id, event_id=event_id
    )
