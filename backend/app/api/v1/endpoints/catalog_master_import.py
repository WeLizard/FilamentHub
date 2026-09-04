"""Administrative XLSX catalog master-import with stateless preview."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.db.session import get_db
from app.models.catalog_import import CatalogImportBatch
from app.models.user import User
from app.schemas.catalog_import import (
    CatalogImportApplyRequest,
    CatalogImportApplyResponse,
    CatalogImportBatchResponse,
    CatalogImportDraft,
    CatalogImportHistoryResponse,
    CatalogImportPreview,
)
from app.services.catalog_master_import_service import (
    MAX_WORKBOOK_BYTES,
    CatalogMasterImportError,
    _public_rows,
    apply_plan,
    build_plan,
    build_template,
    draft_digest,
    issue_confirmation,
    parse_workbook,
    plan_digest,
    summarize,
    verify_confirmation,
)

router = APIRouter(prefix="/admin/catalog/master-import", tags=["admin", "catalog"])


def _raise_service_error(exc: CatalogMasterImportError) -> None:
    status_code = 413 if exc.code == "ERR_CATALOG_IMPORT_FILE_TOO_LARGE" else 409
    if exc.code in {
        "ERR_CATALOG_IMPORT_INVALID_XLSX",
        "ERR_CATALOG_IMPORT_FORMULA_NOT_ALLOWED",
        "ERR_CATALOG_IMPORT_TOO_MANY_ROWS",
        "ERR_CATALOG_IMPORT_EMPTY",
    }:
        status_code = 400
    raise HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "params": {"message": exc.message}},
    )


async def _preview(
    db: AsyncSession, draft: CatalogImportDraft, admin_user_id: int
) -> CatalogImportPreview:
    plan = await build_plan(db, draft, admin_user_id=admin_user_id)
    summary = summarize(plan)
    token = None
    expires_at = None
    if summary["error"] == 0:
        token, expires_at = issue_confirmation(
            user_id=admin_user_id,
            draft_hash=draft_digest(draft),
            calculated_plan_digest=plan_digest(plan),
        )
    return CatalogImportPreview(
        draft=draft,
        rows=_public_rows(plan),
        summary=summary,
        confirmation_token=token,
        confirmation_expires_at=expires_at,
    )


@router.get("/template")
async def download_template(
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    del admin
    return Response(
        content=build_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="filamenthub-catalog-import.xlsx"'},
    )


@router.post("/preview", response_model=CatalogImportPreview)
async def preview_workbook(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> CatalogImportPreview:
    payload = await file.read(MAX_WORKBOOK_BYTES + 1)
    try:
        draft = parse_workbook(payload, file.filename or "catalog.xlsx")
        return await _preview(db, draft, admin.id)
    except CatalogMasterImportError as exc:
        _raise_service_error(exc)


@router.post("/preview-draft", response_model=CatalogImportPreview)
async def preview_edited_draft(
    draft: CatalogImportDraft,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogImportPreview:
    return await _preview(db, draft, admin.id)


@router.post("/apply", response_model=CatalogImportApplyResponse)
async def apply_master_import(
    request: CatalogImportApplyRequest,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CatalogImportApplyResponse:
    try:
        plan = await build_plan(db, request.draft, admin_user_id=admin.id)
        calculated_plan_digest = plan_digest(plan)
        verify_confirmation(
            token=request.confirmation_token,
            user_id=admin.id,
            draft_hash=draft_digest(request.draft),
            calculated_plan_digest=calculated_plan_digest,
        )
        batch = await apply_plan(
            db,
            request.draft,
            plan,
            admin_user_id=admin.id,
        )
        await db.commit()
        return CatalogImportApplyResponse(batch_id=batch.id, summary=batch.summary)
    except CatalogMasterImportError as exc:
        await db.rollback()
        _raise_service_error(exc)
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        # A new identity cannot be row-locked before it exists. A concurrent
        # create is resolved by the unique constraint and requires a new preview.
        _raise_service_error(
            CatalogMasterImportError(
                "ERR_CATALOG_IMPORT_STALE",
                "Catalog changed while applying; review a fresh preview",
            )
        )


@router.get("/history", response_model=CatalogImportHistoryResponse)
async def import_history(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    size: int = Query(20, ge=1, le=100),
) -> CatalogImportHistoryResponse:
    del admin
    total = int(await db.scalar(select(func.count()).select_from(CatalogImportBatch)) or 0)
    batches = (
        (
            await db.execute(
                select(CatalogImportBatch)
                .order_by(CatalogImportBatch.applied_at.desc(), CatalogImportBatch.id.desc())
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    return CatalogImportHistoryResponse(
        total=total,
        items=[
            CatalogImportBatchResponse(
                id=batch.id,
                filename=batch.filename,
                source_sha256=batch.source_sha256,
                applied_by_user_id=batch.applied_by_user_id,
                summary=batch.summary,
                applied_at=batch.applied_at,
            )
            for batch in batches
        ],
    )
