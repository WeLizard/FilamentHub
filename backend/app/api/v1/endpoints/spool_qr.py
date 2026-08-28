"""Owner-only operations for QR identities linked to personal spools."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.qr_identity import (
    QrReplaceMaterialRequest,
    QrRevisionRequest,
    QrRotateRequest,
    UserSpoolQrListResponse,
    UserSpoolQrResponse,
)
from app.services.qr_identity_service import (
    get_user_spool_qr,
    issue_user_spool_qr,
    list_user_spool_qr,
    replace_user_spool_qr_material,
    restore_user_spool_qr,
    retire_user_spool_qr,
    rotate_user_spool_qr,
)
from app.services.qr_service import (
    generate_branded_qr_code_image,
    generate_branded_qr_code_svg,
    generate_qr_code_image,
    generate_qr_code_svg,
)

router = APIRouter(prefix="/spools", tags=["spool-qr"])


@router.get("/qr-codes", response_model=UserSpoolQrListResponse)
async def list_owned_spool_qr_codes(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> UserSpoolQrListResponse:
    """List only QR identities linked to the current user's spools."""
    return await list_user_spool_qr(
        db,
        user=current_user,
        offset=offset,
        limit=limit,
    )


@router.post("/{spool_id}/qr/issue", response_model=UserSpoolQrResponse)
async def issue_or_reprint_spool_qr(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Issue once or return the same active code for a reprint."""
    return await issue_user_spool_qr(db, user=current_user, spool_id=spool_id)


@router.get("/{spool_id}/qr", response_model=UserSpoolQrResponse)
async def get_owned_spool_qr(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Read one existing QR identity without creating it."""
    return await get_user_spool_qr(db, user=current_user, spool_id=spool_id)


@router.post("/{spool_id}/qr/retire", response_model=UserSpoolQrResponse)
async def retire_owned_spool_qr(
    spool_id: int,
    payload: QrRevisionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Begin the explicit seven-day recovery window."""
    return await retire_user_spool_qr(
        db,
        user=current_user,
        spool_id=spool_id,
        revision=payload.revision,
    )


@router.post("/{spool_id}/qr/restore", response_model=UserSpoolQrResponse)
async def restore_owned_spool_qr(
    spool_id: int,
    payload: QrRevisionRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Restore the same token while its recovery window is still open."""
    return await restore_user_spool_qr(
        db,
        user=current_user,
        spool_id=spool_id,
        revision=payload.revision,
    )


@router.post("/{spool_id}/qr/rotate", response_model=UserSpoolQrResponse)
async def rotate_owned_spool_qr(
    spool_id: int,
    payload: QrRotateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Replace a compromised code; a repeated operation key returns the result."""
    return await rotate_user_spool_qr(
        db,
        user=current_user,
        spool_id=spool_id,
        revision=payload.revision,
        idempotency_key=payload.idempotency_key,
    )


@router.post("/{spool_id}/qr/replace-material", response_model=UserSpoolQrResponse)
async def replace_owned_spool_qr_material(
    spool_id: int,
    payload: QrReplaceMaterialRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSpoolQrResponse:
    """Atomically change material and issue the replacement QR to reprint."""
    return await replace_user_spool_qr_material(
        db,
        user=current_user,
        spool_id=spool_id,
        filament_id=payload.filament_id,
        revision=payload.revision,
        idempotency_key=payload.idempotency_key,
        confirm_reprint=payload.confirm_reprint,
    )


@router.get("/{spool_id}/qr/download")
async def download_owned_spool_qr(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    size: int = Query(600, ge=100, le=1200),
    image_format: Annotated[Literal["png", "svg"], Query(alias="format")] = "svg",
    branded: bool = Query(False),
) -> StreamingResponse:
    """Render an already-issued owner code as the classic QR output."""
    qr = await get_user_spool_qr(db, user=current_user, spool_id=spool_id)
    suffix = "-branded" if branded else ""
    if image_format == "svg":
        buffer = (
            generate_branded_qr_code_svg(qr.short_code)
            if branded
            else generate_qr_code_svg(qr.short_code)
        )
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": f'attachment; filename="spool-{spool_id}-qr{suffix}.svg"',
                "Cache-Control": "private, no-store",
            },
        )
    buffer = (
        generate_branded_qr_code_image(qr.short_code, size=size)
        if branded
        else generate_qr_code_image(qr.short_code, size=size)
    )
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="image/png",
        headers={
            "Content-Disposition": (
                f'attachment; filename="spool-{spool_id}-qr-{size}x{size}{suffix}.png"'
            ),
            "Cache-Control": "private, no-store",
        },
    )
