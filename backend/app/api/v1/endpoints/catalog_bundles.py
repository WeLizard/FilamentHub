"""Admin endpoints for catalog bundle lifecycle (RFC §8).

Bundle = admin-only seed of FilamentHub printer catalog from external slicer
bundles (OrcaSlicer system bundle today; PrusaSlicer / Cura / Bambu later).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_BUNDLE_DUPLICATE,
    ERR_BUNDLE_FILE_REQUIRED,
    ERR_BUNDLE_FILE_TOO_LARGE,
    ERR_BUNDLE_IMPORT_FAILED,
    ERR_BUNDLE_NOT_FOUND,
    ERR_BUNDLE_NOT_VALIDATED,
    ERR_BUNDLE_SOURCE_NOT_IMPLEMENTED,
    ERR_BUNDLE_SOURCE_UNSUPPORTED,
    raise_error,
)
from app.db.session import get_db
from app.models.bundle import Bundle, BundleImport, BundleSource
from app.models.user import User
from app.schemas.bundle import (
    BundleCreateResponse,
    BundleDetail,
    BundleImportSummary,
    BundleListResponse,
    BundleSummary,
)
from app.services.bundle_service import BundleService, BundleServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/catalog/bundles", tags=["admin", "catalog"])

MAX_BUNDLE_SIZE_MB = 100
_MAX_BUNDLE_BYTES = MAX_BUNDLE_SIZE_MB * 1024 * 1024


_ERROR_HTTP_STATUS: dict[str, int] = {
    "ERR_BUNDLE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "ERR_BUNDLE_DUPLICATE": status.HTTP_409_CONFLICT,
    "ERR_BUNDLE_SOURCE_UNSUPPORTED": status.HTTP_400_BAD_REQUEST,
    "ERR_BUNDLE_SOURCE_NOT_IMPLEMENTED": status.HTTP_501_NOT_IMPLEMENTED,
    "ERR_BUNDLE_NOT_VALIDATED": status.HTTP_409_CONFLICT,
    "ERR_BUNDLE_IMPORT_FAILED": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _raise_from_service(exc: BundleServiceError) -> None:
    http_status = _ERROR_HTTP_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST)
    raise HTTPException(
        status_code=http_status,
        detail={"code": exc.code, "params": exc.params},
    )


@router.post("", response_model=BundleCreateResponse)
async def upload_bundle(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    source: Annotated[str, Form(...)],
    auto_import: Annotated[bool, Form()] = False,
) -> BundleCreateResponse:
    """Upload a bundle archive, validate inline. Optionally trigger import.

    Body: multipart/form-data { file: <zip>, source: 'orca'|..., auto_import?: bool }
    """
    if file is None or file.filename is None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_BUNDLE_FILE_REQUIRED)

    if source not in BundleSource.ALL:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_BUNDLE_SOURCE_UNSUPPORTED,
            params={"source": source, "allowed": list(BundleSource.ALL)},
        )

    payload = await file.read()
    if len(payload) > _MAX_BUNDLE_BYTES:
        raise_error(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            ERR_BUNDLE_FILE_TOO_LARGE,
            params={
                "size_mb": round(len(payload) / 1024 / 1024, 2),
                "max_mb": MAX_BUNDLE_SIZE_MB,
            },
        )

    service = BundleService(db)
    try:
        bundle = await service.upload(
            file_bytes=payload,
            filename=file.filename,
            source=source,
            uploaded_by_user_id=admin.id,
        )
    except BundleServiceError as exc:
        _raise_from_service(exc)

    if auto_import:
        try:
            await service.import_bundle(
                bundle_id=bundle.id, triggered_by_user_id=admin.id
            )
            await db.commit()
            await db.refresh(bundle)
        except BundleServiceError as exc:
            await db.commit()  # persist failure audit row
            _raise_from_service(exc)
    else:
        await db.commit()

    return BundleCreateResponse(
        bundle_id=bundle.id,
        status=bundle.status,
        validation_summary=bundle.validation_summary,
    )


@router.get("", response_model=BundleListResponse)
async def list_bundles(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    source: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> BundleListResponse:
    """List bundles, paginated, with optional status / source filter."""
    query = select(Bundle).order_by(Bundle.uploaded_at.desc())
    count_query = select(func.count(Bundle.id))

    if status_filter:
        query = query.where(Bundle.status == status_filter)
        count_query = count_query.where(Bundle.status == status_filter)
    if source:
        query = query.where(Bundle.source == source)
        count_query = count_query.where(Bundle.source == source)

    total = (await db.scalar(count_query)) or 0
    offset = (page - 1) * size
    rows = (await db.execute(query.offset(offset).limit(size))).scalars().all()

    return BundleListResponse(
        items=[BundleSummary.model_validate(b) for b in rows],
        total=total,
        page=page,
        size=size,
    )


@router.get("/{bundle_id}", response_model=BundleDetail)
async def get_bundle(
    bundle_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BundleDetail:
    """Fetch one bundle + its import audit log (most recent first)."""
    bundle = await db.get(Bundle, bundle_id)
    if bundle is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BUNDLE_NOT_FOUND, params={"bundle_id": bundle_id})

    imports_rows = (
        await db.execute(
            select(BundleImport)
            .where(BundleImport.bundle_id == bundle_id)
            .order_by(BundleImport.id.desc())
        )
    ).scalars().all()

    base = BundleSummary.model_validate(bundle).model_dump()
    return BundleDetail(
        **base,
        imports=[BundleImportSummary.model_validate(r) for r in imports_rows],
    )


@router.post("/{bundle_id}/validate", response_model=BundleSummary)
async def validate_bundle(
    bundle_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BundleSummary:
    """Re-run validation (e.g. after adapter fix without re-uploading file)."""
    service = BundleService(db)
    try:
        bundle = await service.revalidate(bundle_id)
    except BundleServiceError as exc:
        _raise_from_service(exc)
    await db.commit()
    return BundleSummary.model_validate(bundle)


@router.post("/{bundle_id}/import", response_model=BundleImportSummary)
async def import_bundle(
    bundle_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BundleImportSummary:
    """Trigger import of a validated bundle. Idempotent via content_hash dedup."""
    service = BundleService(db)
    try:
        audit = await service.import_bundle(
            bundle_id=bundle_id, triggered_by_user_id=admin.id
        )
    except BundleServiceError as exc:
        await db.commit()  # persist failure audit row before raising
        _raise_from_service(exc)
    await db.commit()
    return BundleImportSummary.model_validate(audit)


@router.post("/{bundle_id}/rollback", response_model=dict)
async def rollback_bundle(
    bundle_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Detach catalog records linked to this bundle (SET NULL). Records are kept."""
    service = BundleService(db)
    try:
        result = await service.rollback(
            bundle_id=bundle_id, triggered_by_user_id=admin.id
        )
    except BundleServiceError as exc:
        _raise_from_service(exc)
    await db.commit()
    return result
