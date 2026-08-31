"""Read-only, bounded exports of public SKU labels."""

import logging
from dataclasses import asdict, replace
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capacity import Gate
from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_LABEL_BRAND_LOGO_UNAVAILABLE,
    ERR_LABEL_DOES_NOT_FIT,
    ERR_LABEL_RENDER_FAILED,
    ERR_LABEL_UNSUPPORTED_TEXT,
    ERR_QR_BINDING_STATE_CONFLICT,
    raise_error,
)
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.label import LabelExportOptions
from app.services.label_catalog import catalog_label_data, public_brand_logo, public_label_filament
from app.services.label_fonts import UnsupportedLabelText
from app.services.label_layout import SHEET_MEDIA, LabelDoesNotFit, compose_sheet, sheet_positions
from app.services.label_renderer import (
    LabelBrandLogoUnavailable,
    export_label,
    render_label,
    sheet_svg,
)
from app.services.qr_identity_service import get_user_spool_qr

router = APIRouter(prefix="/labels", tags=["labels"])
logger = logging.getLogger(__name__)
label_gate = Gate("label rendering", slots=1, wait_seconds=0.1)

MEDIA_PRESETS = [
    {"width_mm": width, "height_mm": height}
    for width, height in ((40, 30), (50, 30), (62, 29), (54, 25), (63.5, 38.1), (40, 12))
]


def _metadata(filament, locale: str) -> dict:
    data = asdict(catalog_label_data(filament, locale))
    # qr_payload is a renderer input, not a second human-readable metadata
    # field. Keep the established public response shape stable.
    data.pop("qr_payload", None)
    return {
        "data": data,
        "media_presets": MEDIA_PRESETS,
        "classic_presets_mm": [20, 25, 30, 40],
        "sheet_media": {
            key: {"width_mm": size[0], "height_mm": size[1]} for key, size in SHEET_MEDIA.items()
        },
        "brand_logo_available": bool(
            filament.brand.logo_url and filament.brand.logo_url.startswith("/uploads/brand_logos/")
        ),
    }


async def _spool_label_context(
    db: AsyncSession,
    user: User,
    spool_id: int,
    locale: str,
):
    qr = await get_user_spool_qr(db, user=user, spool_id=spool_id)
    if qr.state not in {"active", "linked"}:
        raise_error(409, ERR_QR_BINDING_STATE_CONFLICT)
    filament = await public_label_filament(db, qr.filament_id)
    data = replace(catalog_label_data(filament, locale), qr_payload=qr.short_code)
    return filament, data


@router.get("/filaments/{filament_id}")
async def label_metadata(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Literal["ru", "en", "zh"] = Query("ru"),
) -> dict:
    filament = await public_label_filament(db, filament_id)
    return _metadata(filament, locale)


@router.get("/spools/{spool_id}")
async def spool_label_metadata(
    spool_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: Literal["ru", "en", "zh"] = Query("ru"),
) -> dict:
    filament, _data = await _spool_label_context(db, current_user, spool_id, locale)
    return _metadata(filament, locale)


def _render(data, options, logo_url, download, page=1):
    try:
        logo = public_brand_logo(logo_url) if options.label.show_brand_logo else None
        if download:
            return export_label(data, options, logo)
        rendered = render_label(data, options.label, logo)
        svg, width, height, capacity = sheet_svg(rendered, options, page)
        rendered.update(page_svg=svg, page_width_mm=width, page_height_mm=height, capacity=capacity)
        sheet = compose_sheet(options)
        rendered.update(
            sheet=asdict(sheet),
            page_number=page,
            page_copies=len(sheet_positions(options, sheet, page)),
        )
        rendered.pop("content")
        return rendered
    except LabelBrandLogoUnavailable:
        raise_error(422, ERR_LABEL_BRAND_LOGO_UNAVAILABLE)
    except LabelDoesNotFit:
        raise_error(422, ERR_LABEL_DOES_NOT_FIT)
    except UnsupportedLabelText:
        raise_error(422, ERR_LABEL_UNSUPPORTED_TEXT)
    except (OSError, ValueError):
        logger.warning("Public label rendering failed", exc_info=True)
        raise_error(422, ERR_LABEL_RENDER_FAILED)


@router.post("/filaments/{filament_id}/preview")
@limiter.limit("120/minute")
async def label_preview(
    request: Request,
    filament_id: int,
    options: LabelExportOptions,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, le=50),
) -> dict:
    filament = await public_label_filament(db, filament_id)
    return await label_gate.run(
        _render,
        catalog_label_data(filament, options.label.locale),
        options,
        filament.brand.logo_url,
        False,
        page,
    )


@router.post("/spools/{spool_id}/preview")
@limiter.limit("120/minute")
async def spool_label_preview(
    request: Request,
    spool_id: int,
    options: LabelExportOptions,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1, le=50),
) -> dict:
    filament, data = await _spool_label_context(db, current_user, spool_id, options.label.locale)
    return await label_gate.run(
        _render,
        data,
        options,
        filament.brand.logo_url,
        False,
        page,
    )


@router.post("/filaments/{filament_id}/export")
@limiter.limit("20/minute")
async def label_export(
    request: Request,
    filament_id: int,
    options: LabelExportOptions,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    filament = await public_label_filament(db, filament_id)
    content = await label_gate.run(
        _render,
        catalog_label_data(filament, options.label.locale),
        options,
        filament.brand.logo_url,
        True,
    )
    mime = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}[options.format]
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="label-{filament.id}.{options.format}"',
        },
    )


@router.post("/spools/{spool_id}/export")
@limiter.limit("20/minute")
async def spool_label_export(
    request: Request,
    spool_id: int,
    options: LabelExportOptions,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    filament, data = await _spool_label_context(db, current_user, spool_id, options.label.locale)
    content = await label_gate.run(
        _render,
        data,
        options,
        filament.brand.logo_url,
        True,
    )
    mime = {"svg": "image/svg+xml", "png": "image/png", "pdf": "application/pdf"}[options.format]
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'attachment; filename="spool-label-{spool_id}.{options.format}"',
        },
    )
