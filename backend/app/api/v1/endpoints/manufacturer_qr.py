"""Organization-scoped manufacturer QR batch API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.qr_identity import (
    ManufacturerQrBatchCreateRequest,
    ManufacturerQrBatchListResponse,
    ManufacturerQrBatchResponse,
    ManufacturerQrExceptionRequest,
    ManufacturerQrExceptionResponse,
    ManufacturerQrPayloadPage,
)
from app.services.qr_identity_service import (
    create_manufacturer_qr_batch,
    get_manufacturer_qr_batch,
    list_manufacturer_qr_batches,
    manufacturer_qr_payload_page,
    set_manufacturer_qr_exception,
)

router = APIRouter(prefix="/manufacturer/qr-batches", tags=["manufacturer-qr"])


@router.post(
    "",
    response_model=ManufacturerQrBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_qr_batch(
    payload: ManufacturerQrBatchCreateRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManufacturerQrBatchResponse:
    """Create one replay-safe compact SKU or serialized batch."""
    return await create_manufacturer_qr_batch(
        db,
        user=current_user,
        payload=payload,
        idempotency_key=idempotency_key,
    )


@router.get("", response_model=ManufacturerQrBatchListResponse)
async def list_qr_batches(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> ManufacturerQrBatchListResponse:
    """List bounded batch history for the selected authorized workspace."""
    return await list_manufacturer_qr_batches(
        db,
        user=current_user,
        offset=offset,
        limit=limit,
    )


@router.get("/{public_id}", response_model=ManufacturerQrBatchResponse)
async def get_qr_batch(
    public_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManufacturerQrBatchResponse:
    """Read one immutable manifest revision in the selected workspace."""
    return await get_manufacturer_qr_batch(db, user=current_user, public_id=public_id)


@router.get("/{public_id}/payloads", response_model=ManufacturerQrPayloadPage)
async def get_qr_batch_payloads(
    public_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(250, ge=1, le=1000),
) -> ManufacturerQrPayloadPage:
    """Return a bounded deterministic page for files or equipment adapters."""
    return await manufacturer_qr_payload_page(
        db,
        user=current_user,
        public_id=public_id,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{public_id}/exceptions",
    response_model=ManufacturerQrExceptionResponse,
)
async def set_qr_batch_exception(
    public_id: str,
    payload: ManufacturerQrExceptionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ManufacturerQrExceptionResponse:
    """Record or restore sparse scrap/revoke state without expanding the batch."""
    return await set_manufacturer_qr_exception(
        db,
        user=current_user,
        public_id=public_id,
        ordinal=payload.ordinal,
        action=payload.action,
        idempotency_key=payload.idempotency_key,
    )
