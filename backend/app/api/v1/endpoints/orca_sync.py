"""Endpoints for OrcaSlicer synchronisation (printer & print profiles)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user_by_api_key
from app.db.session import get_db
from app.models.print_profile import PrintProfile
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.schemas.orca_sync import (
    OrcaSyncResult,
    PrintProfileSyncRequest,
    PrintProfileSyncResponse,
    PrinterProfileSyncRequest,
    PrinterProfileSyncResponse,
)
from app.schemas.print_profile import PrintProfileListResponse, PrintProfileResponse
from app.schemas.printer_profile import PrinterProfileListResponse, PrinterProfileResponse
from app.services.preset_moderation import validate_text_field
from app.services.slug_service import generate_unique_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orcaslicer", tags=["orcaslicer"])


async def _ensure_printer_id(
    *,
    db: AsyncSession,
    printer_id: int | None,
    printer_slug: str | None,
) -> int | None:
    """Resolve printer ID either by explicit ID or by slug."""
    if printer_id:
        printer = await db.get(Printer, printer_id)
        if printer:
            return printer.id
        return None
    if printer_slug:
        result = await db.execute(select(Printer).where(Printer.slug == printer_slug))
        printer = result.scalar_one_or_none()
        if printer:
            return printer.id
    return None


def _merge_extra_metadata(
    metadata: dict[str, Any] | None,
    condition: str | None,
) -> dict[str, Any] | None:
    """Merge metadata dict with compatibility condition, returning None if empty."""
    merged: dict[str, Any] = dict(metadata or {})
    if condition:
        merged["compatible_printers_condition"] = condition
    return merged or None


async def _upsert_printer_profile(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    from app.schemas.orca_sync import OrcaPrinterProfilePayload

    if not isinstance(payload, OrcaPrinterProfilePayload):
        raise ValueError("Invalid payload type for printer profile import")

    is_valid, error_msg = await validate_text_field(payload.name, db, "Название профиля принтера")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "Описание профиля принтера"),
        (payload.notes, "Заметки к профилю принтера"),
    ]:
        if field_value:
            is_valid, error_msg = await validate_text_field(field_value, db, label)
            if not is_valid:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=error_msg,
                )

    profile: PrinterProfile | None = None
    if payload.fhub_id:
        profile = await db.get(PrinterProfile, payload.fhub_id)
        if profile is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Printer profile not found in FilamentHub",
            )
    elif payload.slug:
        result = await db.execute(
            select(PrinterProfile).where(
                PrinterProfile.slug == payload.slug,
                PrinterProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalar_one_or_none()

    printer_id = await _ensure_printer_id(
        db=db,
        printer_id=payload.printer_id,
        printer_slug=payload.printer_slug,
    )

    if profile:
        if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=profile.id,
                status="skipped",
                message="Недостаточно прав для обновления профиля",
            )

        if payload.slug and payload.slug != profile.slug:
            profile.slug = await generate_unique_slug(
                db=db,
                model=PrinterProfile,
                source=payload.slug,
                fallback=f"printer-profile-{current_user.id}",
                exclude_id=profile.id,
            )

        profile.name = payload.name
        profile.description = payload.description
        profile.printer_id = printer_id
        profile.owner_user_id = profile.owner_user_id or current_user.id
        profile.active = payload.active if payload.active is not None else profile.active
        profile.source = payload.source or profile.source
        profile.vendor = payload.vendor or profile.vendor
        profile.setting_id = payload.setting_id or profile.setting_id
        profile.external_id = payload.external_id or profile.external_id
        profile.default_print_profile_slug = (
            payload.default_print_profile_slug or profile.default_print_profile_slug
        )
        if payload.nozzle_diameters is not None:
            profile.nozzle_diameters = payload.nozzle_diameters
        if payload.printable_area is not None:
            profile.printable_area = payload.printable_area
        if payload.printable_height_mm is not None:
            profile.printable_height_mm = payload.printable_height_mm
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        profile.orcaslicer_settings = payload.orcaslicer_settings or {}
        profile.start_gcode = payload.start_gcode
        profile.end_gcode = payload.end_gcode
        profile.notes = payload.notes
        profile.is_official = profile.is_official if current_user.role != UserRole.ADMIN else profile.is_official

        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=profile.id,
            status="updated",
            message="Profile updated",
        )

    slug_source = payload.slug or payload.name
    slug = await generate_unique_slug(
        db=db,
        model=PrinterProfile,
        source=slug_source,
        fallback=f"printer-profile-{current_user.id}",
    )

    profile = PrinterProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        printer_id=printer_id,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else False,
        source=payload.source or "system",
        vendor=payload.vendor,
        setting_id=payload.setting_id,
        external_id=payload.external_id,
        default_print_profile_slug=payload.default_print_profile_slug,
        nozzle_diameters=payload.nozzle_diameters,
        printable_area=payload.printable_area,
        printable_height_mm=payload.printable_height_mm,
        extra_metadata=payload.extra_metadata,
        orcaslicer_settings=payload.orcaslicer_settings or {},
        start_gcode=payload.start_gcode,
        end_gcode=payload.end_gcode,
        notes=payload.notes,
    )
    db.add(profile)
    await db.flush()

    return OrcaSyncResult(
        external_id=payload.external_id,
        fhub_id=profile.id,
        status="created",
        message="Profile created",
    )


async def _upsert_print_profile(
    *,
    payload,
    current_user: User,
    db: AsyncSession,
) -> OrcaSyncResult:
    from app.schemas.orca_sync import OrcaPrintProfilePayload

    if not isinstance(payload, OrcaPrintProfilePayload):
        raise ValueError("Invalid payload type for print profile import")

    is_valid, error_msg = await validate_text_field(payload.name, db, "Название профиля печати")
    if not is_valid:
        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=payload.fhub_id,
            status="error",
            message=error_msg,
        )

    for field_value, label in [
        (payload.description, "Описание профиля печати"),
        (payload.notes, "Заметки к профилю печати"),
    ]:
        if field_value:
            is_valid, error_msg = await validate_text_field(field_value, db, label)
            if not is_valid:
                return OrcaSyncResult(
                    external_id=payload.external_id,
                    fhub_id=payload.fhub_id,
                    status="error",
                    message=error_msg,
                )

    profile: PrintProfile | None = None
    if payload.fhub_id:
        profile = await db.get(PrintProfile, payload.fhub_id)
        if profile is None:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=payload.fhub_id,
                status="error",
                message="Print profile not found in FilamentHub",
            )
    elif payload.slug:
        result = await db.execute(
            select(PrintProfile).where(
                PrintProfile.slug == payload.slug,
                PrintProfile.owner_user_id == current_user.id,
            )
        )
        profile = result.scalar_one_or_none()

    compatible_printers = (
        [str(item) for item in payload.compatible_printers] if payload.compatible_printers else None
    )
    compatible_filaments = (
        [str(item) for item in payload.compatible_filaments] if payload.compatible_filaments else None
    )

    if profile:
        if profile.owner_user_id not in (None, current_user.id) and current_user.role != UserRole.ADMIN:
            return OrcaSyncResult(
                external_id=payload.external_id,
                fhub_id=profile.id,
                status="skipped",
                message="Недостаточно прав для обновления профиля",
            )

        if payload.slug and payload.slug != profile.slug:
            profile.slug = await generate_unique_slug(
                db=db,
                model=PrintProfile,
                source=payload.slug,
                fallback=f"print-profile-{current_user.id}",
                exclude_id=profile.id,
            )

        profile.name = payload.name
        profile.description = payload.description
        profile.category = payload.category
        profile.owner_user_id = profile.owner_user_id or current_user.id
        profile.active = payload.active if payload.active is not None else profile.active
        profile.source = payload.source or profile.source
        profile.vendor = payload.vendor or profile.vendor
        profile.setting_id = payload.setting_id or profile.setting_id
        profile.external_id = payload.external_id or profile.external_id
        profile.quality_tier = payload.quality_tier or profile.quality_tier
        profile.default_nozzle = payload.default_nozzle or profile.default_nozzle
        if payload.layer_height_mm is not None:
            profile.layer_height_mm = payload.layer_height_mm
        profile.compatible_printers = compatible_printers
        profile.compatible_filaments = compatible_filaments
        profile.orcaslicer_settings = payload.orcaslicer_settings or {}
        if payload.extra_metadata:
            profile.extra_metadata = payload.extra_metadata
        if payload.compatible_printers_condition:
            extra = dict(profile.extra_metadata or {})
            extra["compatible_printers_condition"] = payload.compatible_printers_condition
            profile.extra_metadata = extra
        profile.notes = payload.notes
        profile.is_official = profile.is_official if current_user.role != UserRole.ADMIN else profile.is_official

        return OrcaSyncResult(
            external_id=payload.external_id,
            fhub_id=profile.id,
            status="updated",
            message="Profile updated",
        )

    slug_source = payload.slug or payload.name
    slug = await generate_unique_slug(
        db=db,
        model=PrintProfile,
        source=slug_source,
        fallback=f"print-profile-{current_user.id}",
    )

    profile = PrintProfile(
        name=payload.name,
        slug=slug,
        description=payload.description,
        category=payload.category,
        owner_user_id=current_user.id,
        is_official=False,
        active=payload.active if payload.active is not None else False,
        source=payload.source or "system",
        vendor=payload.vendor,
        external_id=payload.external_id,
        setting_id=payload.setting_id,
        quality_tier=payload.quality_tier,
        default_nozzle=payload.default_nozzle,
        layer_height_mm=payload.layer_height_mm,
        compatible_printers=compatible_printers,
        compatible_filaments=compatible_filaments,
        orcaslicer_settings=payload.orcaslicer_settings or {},
        extra_metadata=_merge_extra_metadata(payload.extra_metadata, payload.compatible_printers_condition),
        notes=payload.notes,
    )
    db.add(profile)
    await db.flush()

    return OrcaSyncResult(
        external_id=payload.external_id,
        fhub_id=profile.id,
        status="created",
        message="Profile created",
    )


@router.get("/printer-profiles", response_model=PrinterProfileListResponse)
async def list_printer_profiles_for_sync(
    current_user: Annotated[User, Depends(get_current_user_by_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    updated_since: datetime | None = Query(
        default=None,
        description="Возвращать только профили, обновленные после указанной даты (ISO 8601).",
    ),
    include_official: bool = Query(
        default=True,
        description="Включить официальные профили FilamentHub в выдачу.",
    ),
) -> PrinterProfileListResponse:
    """Return printer profiles for OrcaSlicer synchronisation."""
    query = select(PrinterProfile)
    if include_official:
        query = query.where(
            or_(
                PrinterProfile.owner_user_id == current_user.id,
                PrinterProfile.is_official.is_(True),
            )
        )
    else:
        query = query.where(PrinterProfile.owner_user_id == current_user.id)

    if updated_since:
        query = query.where(PrinterProfile.updated_at >= updated_since)

    query = query.order_by(PrinterProfile.updated_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    items = [PrinterProfileResponse.model_validate(profile) for profile in profiles]
    total = len(items)

    return PrinterProfileListResponse(
        items=items,
        total=total,
        page=1,
        size=total,
        pages=1,
    )


@router.get("/print-profiles", response_model=PrintProfileListResponse)
async def list_print_profiles_for_sync(
    current_user: Annotated[User, Depends(get_current_user_by_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
    updated_since: datetime | None = Query(
        default=None,
        description="Возвращать только профили, обновленные после указанной даты (ISO 8601).",
    ),
    include_official: bool = Query(
        default=True,
        description="Включить официальные профили FilamentHub в выдачу.",
    ),
) -> PrintProfileListResponse:
    """Return print profiles for OrcaSlicer synchronisation."""
    query = select(PrintProfile)
    if include_official:
        query = query.where(
            or_(
                PrintProfile.owner_user_id == current_user.id,
                PrintProfile.is_official.is_(True),
            )
        )
    else:
        query = query.where(PrintProfile.owner_user_id == current_user.id)

    if updated_since:
        query = query.where(PrintProfile.updated_at >= updated_since)

    query = query.order_by(PrintProfile.updated_at.desc())
    result = await db.execute(query)
    profiles = result.scalars().all()

    items = [PrintProfileResponse.model_validate(profile) for profile in profiles]
    total = len(items)

    return PrintProfileListResponse(
        items=items,
        total=total,
        page=1,
        size=total,
        pages=1,
    )


@router.post(
    "/printer-profiles/import",
    response_model=PrinterProfileSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def import_printer_profiles(
    payload: PrinterProfileSyncRequest,
    current_user: Annotated[User, Depends(get_current_user_by_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterProfileSyncResponse:
    """Import or update printer profiles submitted by OrcaSlicer."""
    results: list[OrcaSyncResult] = []

    for item in payload.profiles:
        try:
            result = await _upsert_printer_profile(
                payload=item,
                current_user=current_user,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Failed to sync printer profile: %s", exc.detail)
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while syncing printer profile")
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=f"Unexpected error: {exc}",
            )
        results.append(result)

    await db.commit()
    return PrinterProfileSyncResponse(results=results)


@router.post(
    "/print-profiles/import",
    response_model=PrintProfileSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def import_print_profiles(
    payload: PrintProfileSyncRequest,
    current_user: Annotated[User, Depends(get_current_user_by_api_key)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrintProfileSyncResponse:
    """Import or update print profiles submitted by OrcaSlicer."""
    results: list[OrcaSyncResult] = []

    for item in payload.profiles:
        try:
            result = await _upsert_print_profile(
                payload=item,
                current_user=current_user,
                db=db,
            )
        except HTTPException as exc:
            logger.warning("Failed to sync print profile: %s", exc.detail)
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=exc.detail,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while syncing print profile")
            result = OrcaSyncResult(
                external_id=getattr(item, "external_id", None),
                fhub_id=getattr(item, "fhub_id", None),
                status="error",
                message=f"Unexpected error: {exc}",
            )
        results.append(result)

    await db.commit()
    return PrintProfileSyncResponse(results=results)


