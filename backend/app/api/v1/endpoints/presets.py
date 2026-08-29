"""Preset endpoints."""

import json
import logging
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    get_current_active_user,
    get_current_active_user_optional,
    require_preset_read,
)
from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_EXPORT_MISSING_FIELDS,
    ERR_EXPORT_PRESET_ERROR,
    ERR_FILAMENT_NO_PRESETS,
    ERR_FILAMENT_NOT_FOUND,
    ERR_INVALID_FILENAME,
    ERR_INVALID_PRESET_SETTINGS,
    ERR_NO_PERMISSION_DELETE_PRESET,
    ERR_NO_PERMISSION_EDIT_PRESET,
    ERR_OFFICIAL_PRESET_COMPANY_ONLY,
    ERR_OFFICIAL_VERIFIED_ONLY,
    ERR_ONLY_OWN_BRAND_OFFICIAL,
    ERR_PRESET_ALREADY_ACTIVE,
    ERR_PRESET_FILAMENT_REQUIRED,
    ERR_PRESET_NOT_FOUND,
    ERR_PRESET_NOT_OWNER,
    ERR_PRESET_OWNERSHIP_IMMUTABLE,
    ERR_PRESET_VERSION_NOT_FOUND,
    ERR_PRINTER_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_FOUND,
    ERR_PRINTER_PROFILE_NOT_LINKED,
    ERR_WEIGHTED_PRESET_NO_DELETE,
    ERR_WEIGHTED_PRESET_READONLY,
    raise_error,
)
from app.core.utils import like_pattern
from app.db.session import get_db
from app.models.filament import Filament
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.preset import (
    OfficialPresetCreate,
    PresetActivateRequest,
    PresetCreate,
    PresetDraftAnalysisResponse,
    PresetDraftMetricRequest,
    PresetDraftQueueResponse,
    PresetListResponse,
    PresetResponse,
    PresetUpdate,
    RecommendedForPrinterResponse,
    RecommendedPresetItem,
    RecommendedPresetResponse,
)
from app.schemas.printer import PrinterResponse
from app.services.download_filename import attachment_content_disposition, safe_download_stem
from app.services.notification_service import notify_preset_deleted, notify_preset_updated
from app.services.orcaslicer_exporter import generate_profile_info, preset_to_orcaslicer_json
from app.services.orcaslicer_preset_contract import (
    apply_structured_filament_updates,
    extract_structured_filament_values,
    is_allowed_orca_preset_name,
    is_valid_orca_preset_name,
    validate_orca_filament_settings,
)
from app.services.preset_matcher import get_recommended_presets
from app.services.preset_moderation import moderate_preset
from app.services.preset_recommender import get_recommended_preset_values

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/presets", tags=["presets"])


def _serialize_moderation_reason(reason: Any) -> str | None:
    if reason is None:
        return None
    if isinstance(reason, (dict, list)):
        return json.dumps(reason, ensure_ascii=False)
    return str(reason)


async def _can_update_preset(
    db: AsyncSession,
    current_user: User,
    preset: Preset,
    filament: Filament | None,
) -> bool:
    """Respect personal authorship and Organization ownership."""
    from app.services.preset_access import can_manage_preset

    return await can_manage_preset(db, current_user, preset, filament)


async def _require_official_publication_authority(
    db: AsyncSession,
    current_user: User,
    filament: Filament,
) -> int | None:
    """Revalidate the active Brand + Organization boundary at publication time."""
    from app.services.preset_access import official_preset_organization_id

    organization_id = await official_preset_organization_id(db, current_user, filament)
    if current_user.role != UserRole.ADMIN and organization_id is None:
        from app.models.brand import Brand

        brand = await db.get(Brand, filament.brand_id)
        if brand is None or not brand.verified:
            raise_error(403, ERR_OFFICIAL_VERIFIED_ONLY)
        raise_error(403, ERR_ONLY_OWN_BRAND_OFFICIAL)
    return organization_id


async def _finish_created_preset(
    *,
    db: AsyncSession,
    current_user: User,
    preset: Preset,
    printer_ids: list[int],
) -> PresetResponse:
    """Persist one new preset and its shared sync/version bookkeeping."""
    db.add(preset)
    await db.flush()

    from app.services.preset_publication import apply_managed_orca_identity

    apply_managed_orca_identity(preset)

    from app.models.user_saved_preset import UserSavedPreset

    db.add(UserSavedPreset(user_id=current_user.id, preset_id=preset.id, sync=True))

    for index, printer_id in enumerate(printer_ids):
        printer = await db.get(Printer, printer_id)
        if printer is None:
            continue
        db.add(
            PresetPrinter(
                preset_id=preset.id,
                printer_id=printer_id,
                is_primary=index == 0,
            )
        )

    from app.models.preset_version import PresetVersionSource
    from app.services import preset_version_service

    await preset_version_service.record_version(
        db,
        preset,
        source=PresetVersionSource.WEB_EDIT,
        user_id=current_user.id,
    )
    await db.commit()

    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.id == preset.id)
    )
    created = result.scalar_one()
    payload = PresetResponse.model_validate(created).model_dump()
    payload["printers"] = [
        PrinterResponse.model_validate(link.printer).model_dump()
        for link in created.printer_links
    ]
    return PresetResponse(**payload)


@router.get("/", response_model=PresetListResponse)
async def list_presets(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User | None, Depends(get_current_active_user_optional)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    filament_id: int | None = Query(None, gt=0),
    printer_id: int | None = Query(None, gt=0, description="Фильтр по принтеру"),
    is_official: bool | None = Query(None),
    user_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, max_length=120),
    ids: str | None = Query(None, description="Comma-separated preset IDs to fetch"),
) -> PresetListResponse:
    """Получить список пресетов."""
    private_user_scope = bool(
        user_id is not None
        and current_user is not None
        and (current_user.id == user_id or current_user.role == UserRole.ADMIN)
    )
    public_visibility = (
        Preset.active.is_(True)
        & or_(
            Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
            Preset.is_official.is_(True),
        )
    )

    # Build query
    query = select(Preset).options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))

    # Filter by explicit IDs (batch fetch — always enforce visibility)
    if ids:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if id_list:
            query = query.where(Preset.id.in_(id_list))
            if active_only:
                query = query.where(Preset.active.is_(True))
            if user_id is not None:
                query = query.where(Preset.user_id == user_id)
            if not private_user_scope:
                query = query.where(public_visibility)
            result = await db.execute(query.limit(len(id_list)))
            items = list(result.unique().scalars().all())
            total = len(items)
            responses = []
            for p in items:
                response = (
                    PresetResponse.model_validate(p)
                    if private_user_scope
                    else PresetResponse.model_validate_public(p)
                )
                d = response.model_dump()
                d["printers"] = [
                    PrinterResponse.model_validate(link.printer).model_dump()
                    for link in p.printer_links
                ]
                responses.append(PresetResponse(**d))
            return PresetListResponse(items=responses, total=total, page=1, size=len(id_list), pages=1)

    if active_only:
        query = query.where(Preset.active.is_(True))
    if filament_id:
        query = query.where(Preset.filament_id == filament_id)
    if printer_id:
        # Фильтруем пресеты, связанные с указанным принтером
        query = query.join(PresetPrinter).where(PresetPrinter.printer_id == printer_id)
    if is_official is not None:
        query = query.where(Preset.is_official == is_official)
    if user_id is not None:
        query = query.where(Preset.user_id == user_id)
    if not private_user_scope:
        query = query.where(public_visibility)
    if search:
        query = query.where(Preset.name.ilike(like_pattern(search), escape="\\"))

    # Count total
    count_query = select(func.count()).select_from(Preset)
    if active_only:
        count_query = count_query.where(Preset.active.is_(True))
    if filament_id:
        count_query = count_query.where(Preset.filament_id == filament_id)
    if printer_id:
        count_query = count_query.join(PresetPrinter).where(PresetPrinter.printer_id == printer_id)
    if is_official is not None:
        count_query = count_query.where(Preset.is_official == is_official)
    if user_id is not None:
        count_query = count_query.where(Preset.user_id == user_id)
    if not private_user_scope:
        count_query = count_query.where(public_visibility)
    if search:
        count_query = count_query.where(Preset.name.ilike(like_pattern(search), escape="\\"))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Pagination
    pages = (total + size - 1) // size
    offset = (page - 1) * size
    query = query.offset(offset).limit(size)

    # Execute query
    result = await db.execute(query)
    presets = result.scalars().unique().all()

    # Преобразуем пресеты в ответ с принтерами
    preset_responses = []
    for preset in presets:
        response = (
            PresetResponse.model_validate(preset)
            if private_user_scope
            else PresetResponse.model_validate_public(preset)
        )
        preset_dict = response.model_dump()
        preset_dict["printers"] = [
            PrinterResponse.model_validate(link.printer).model_dump()
            for link in preset.printer_links
        ]
        preset_responses.append(PresetResponse(**preset_dict))

    return PresetListResponse(
        items=preset_responses,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


def _build_recommended_items(
    scored: list[Any],
    saved_by_preset_id: dict[int, UserSavedPreset] | None = None,
) -> list[RecommendedPresetItem]:
    """Serialize scored presets into API items (shared by the recommendation routes)."""
    items: list[RecommendedPresetItem] = []
    saved_by_preset_id = saved_by_preset_id or {}
    for entry in scored:
        preset_dict = PresetResponse.model_validate_public(entry.preset).model_dump()
        preset_dict["printers"] = [
            PrinterResponse.model_validate(link.printer).model_dump()
            for link in entry.preset.printer_links
            if link.printer is not None
        ]
        saved = saved_by_preset_id.get(entry.preset.id)
        items.append(
            RecommendedPresetItem(
                preset=PresetResponse(**preset_dict),
                match_score=round(entry.match_score, 3),
                match_reason=entry.match_reason,
                compatibility_status=entry.compatibility_status,
                compatibility_coverage=round(entry.compatibility_coverage, 3),
                compatibility_checks=[
                    {
                        "kind": check.kind,
                        "status": check.status,
                        "required_value": check.required_value,
                        "available_value": check.available_value,
                        "unit": check.unit,
                    }
                    for check in entry.compatibility_checks
                ],
                hard_conflicts=entry.hard_conflicts,
                saved=saved is not None,
                sync_enabled=saved.sync if saved is not None else None,
            )
        )
    return items


@router.get("/draft-analyses", response_model=PresetDraftQueueResponse)
async def get_preset_draft_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    limit: int = Query(100, ge=1, le=200),
) -> PresetDraftQueueResponse:
    """Return one compact, batch-computed review queue for the current user."""
    drafts = list(await db.scalars(
        select(Preset)
        .where(
            Preset.user_id == current_user.id,
            Preset.active.is_(False),
        )
        .order_by(Preset.updated_at.desc(), Preset.id.desc())
        .limit(limit)
    ))
    from app.services.preset_draft_analysis import analyze_preset_drafts

    items = await analyze_preset_drafts(db, drafts)
    counts = {
        state: sum(item.review_state == state for item in items)
        for state in ("ready", "almost_ready", "needs_decision", "ambiguous")
    }
    return PresetDraftQueueResponse(
        items=items,
        total=len(items),
        ready=counts["ready"],
        almost_ready=counts["almost_ready"],
        needs_decision=counts["needs_decision"],
        ambiguous=counts["ambiguous"],
    )


@router.post("/draft-events", status_code=204)
async def record_draft_metric(
    data: PresetDraftMetricRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    """Record a category only: no draft, user or source payload is persisted."""
    from app.services.preset_funnel_metrics import record_preset_funnel_event

    record_preset_funnel_event(db, data.event_type)
    await db.commit()
    return Response(status_code=204)


@router.get("/recommended-for-printer", response_model=RecommendedForPrinterResponse)
async def recommended_for_printer(
    db: Annotated[AsyncSession, Depends(get_db)],
    printer_id: int = Query(..., gt=0),
    filament_id: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=100),
) -> RecommendedForPrinterResponse:
    """Топ пресетов под конкретный принтер (публичный каталог).

    Скоринг детерминированный: пресет матчится против привязанных к нему принтеров,
    берётся лучший уровень (точный принтер / та же модель / семейство / бренд / близкие
    характеристики) плюс бонусы за официальность/рейтинг.
    """
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    scored = await get_recommended_presets(db, printer, filament_id, limit)

    return RecommendedForPrinterResponse(
        printer_id=printer.id,
        printer_name=printer.name,
        items=_build_recommended_items(scored),
    )


@router.get("/recommended-for-configuration", response_model=RecommendedForPrinterResponse)
async def recommended_for_configuration(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    printer_profile_id: int = Query(..., gt=0),
    physical_printer_id: int | None = Query(None, gt=0),
    filament_id: int | None = Query(None, gt=0),
    limit: int = Query(20, ge=1, le=100),
) -> RecommendedForPrinterResponse:
    """Catalog preset recommendations for a chosen Orca configuration.

    The configuration (PrinterProfile) resolves the catalog printer context on
    the backend — the frontend never derives the catalog model itself. If a
    physical printer is supplied, it must belong to the user and be linked to
    the configuration. The connection endpoint/IP is never part of identity.
    """
    profile = await db.get(PrinterProfile, printer_profile_id)
    if profile is None or profile.owner_user_id != current_user.id:
        # Recommendations run against the user's own configurations only; shared
        # official profiles are not selectable here (the picker loads owned only).
        raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)

    if physical_printer_id is not None:
        device = await db.get(UserPrinterDevice, physical_printer_id)
        if device is None or device.user_id != current_user.id:
            raise_error(404, ERR_DEVICE_NOT_FOUND)
        linked = (
            await db.execute(
                select(UserPrinterProfileLink.id)
                .where(
                    UserPrinterProfileLink.physical_printer_id == physical_printer_id,
                    UserPrinterProfileLink.printer_profile_id == printer_profile_id,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if linked is None:
            raise_error(400, ERR_PRINTER_PROFILE_NOT_LINKED)

    if profile.printer_id is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    printer = await db.get(Printer, profile.printer_id)
    if printer is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    scored = await get_recommended_presets(
        db,
        printer,
        filament_id,
        limit,
        printer_profile=profile,
    )

    preset_ids = [entry.preset.id for entry in scored]
    saved_by_preset_id: dict[int, UserSavedPreset] = {}
    if preset_ids:
        saved_rows = await db.scalars(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == current_user.id,
                UserSavedPreset.preset_id.in_(preset_ids),
            )
        )
        saved_by_preset_id = {row.preset_id: row for row in saved_rows}

    return RecommendedForPrinterResponse(
        printer_id=printer.id,
        printer_name=printer.name,
        items=_build_recommended_items(scored, saved_by_preset_id),
    )


@router.get("/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User | None = Depends(get_current_active_user_optional),
) -> PresetResponse:
    """Получить пресет по ID."""
    # Загружаем пресет БЕЗ printer_links (таблица может не существовать)
    result = await db.execute(
        select(Preset).where(Preset.id == preset_id)
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    filament = await db.get(Filament, preset.filament_id) if preset.filament_id else None
    is_owner_or_admin = bool(
        current_user
        and await _can_update_preset(db, current_user, preset, filament)
    )

    # An Orca draft is private evidence of one account. Merely having a stale
    # saved-preset row must never expose it to another user.
    if not preset.active:
        if not is_owner_or_admin:
            raise_error(404, ERR_PRESET_NOT_FOUND)

    # Pending/rejected community publication is visible only to its author and
    # admins. The unauthenticated case must not fall through accidentally.
    if (
        preset.moderation_status != PresetModerationStatus.APPROVED
        and not preset.is_official
        and not is_owner_or_admin
    ):
        raise_error(404, ERR_PRESET_NOT_FOUND)

    # Преобразуем пресет в ответ (без printers, так как таблица может не существовать)
    response = (
        PresetResponse.model_validate(preset)
        if is_owner_or_admin
        else PresetResponse.model_validate_public(preset)
    )
    preset_dict = response.model_dump()
    preset_dict["printers"] = []  # Пустой массив, так как printer_links не загружаем
    return PresetResponse(**preset_dict)


@router.get("/{preset_id}/draft-analysis", response_model=PresetDraftAnalysisResponse)
async def get_preset_draft_analysis(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetDraftAnalysisResponse:
    """Return review suggestions without changing the imported preset."""
    preset = await db.get(Preset, preset_id)
    if preset is None:
        raise_error(404, ERR_PRESET_NOT_FOUND)
    if preset.user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    from app.services.preset_draft_analysis import analyze_preset_draft

    return await analyze_preset_draft(db, preset)


@router.post("/", response_model=PresetResponse, status_code=201)
async def create_preset(
    data: PresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Создать новый пресет."""
    from app.models.filament import Filament

    # Проверка существования filament
    filament_result = await db.execute(select(Filament).where(Filament.id == data.filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    if not is_valid_orca_preset_name(data.name):
        raise_error(400, ERR_INVALID_FILENAME)
    try:
        validate_orca_filament_settings(data.orcaslicer_settings)
    except ValueError:
        raise_error(422, ERR_INVALID_PRESET_SETTINGS)

    if data.is_official:
        raise_error(403, ERR_OFFICIAL_PRESET_COMPANY_ONLY)

    preset = Preset(
        filament_id=data.filament_id,
        user_id=current_user.id,
        created_by_user_id=current_user.id,
        organization_id=None,
        name=data.name,
        description=data.description,
        extruder_temp=data.extruder_temp,
        bed_temp=data.bed_temp,
        flow_rate=data.flow_rate,
        fan_speed=data.fan_speed,
        retraction_length=data.retraction_length,
        retraction_speed=data.retraction_speed,
        is_official=False,
        orcaslicer_settings=data.orcaslicer_settings,
        active=True,
    )

    moderation_status, moderation_reason = await moderate_preset(
        preset,
        filament,
        db,
        is_official=False,
        allow_manual_review=False,
    )
    if moderation_status == PresetModerationStatus.REJECTED:
        raise HTTPException(status_code=400, detail=moderation_reason)
    preset.moderation_status = moderation_status
    preset.moderation_reason = (
        _serialize_moderation_reason(moderation_reason)
        if moderation_status == PresetModerationStatus.PENDING
        else None
    )
    return await _finish_created_preset(
        db=db,
        current_user=current_user,
        preset=preset,
        printer_ids=data.printer_ids,
    )


@router.post("/official", response_model=PresetResponse, status_code=201)
async def create_official_preset(
    data: OfficialPresetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Create a distinct Organization-owned preset, optionally from a source."""
    filament = await db.get(Filament, data.filament_id)
    if filament is None:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    if not is_valid_orca_preset_name(data.name):
        raise_error(400, ERR_INVALID_FILENAME)
    try:
        validate_orca_filament_settings(data.orcaslicer_settings)
    except ValueError:
        raise_error(422, ERR_INVALID_PRESET_SETTINGS)

    organization_id = await _require_official_publication_authority(
        db, current_user, filament
    )
    source_preset = None
    if data.source_preset_id is not None:
        source_preset = await db.get(Preset, data.source_preset_id)
        source_visible = bool(
            source_preset
            and not source_preset.is_official
            and not source_preset.is_weighted
            and source_preset.filament_id == data.filament_id
            and (
                source_preset.user_id == current_user.id
                or (
                    source_preset.active
                    and source_preset.moderation_status in PUBLIC_PRESET_STATUSES
                )
            )
        )
        if not source_visible:
            raise_error(404, ERR_PRESET_NOT_FOUND)

    preset = Preset(
        filament_id=data.filament_id,
        user_id=None,
        created_by_user_id=current_user.id,
        organization_id=organization_id,
        derived_from_preset_id=source_preset.id if source_preset else None,
        name=data.name,
        description=data.description,
        extruder_temp=data.extruder_temp,
        bed_temp=data.bed_temp,
        flow_rate=data.flow_rate,
        fan_speed=data.fan_speed,
        retraction_length=data.retraction_length,
        retraction_speed=data.retraction_speed,
        is_official=True,
        orcaslicer_settings=data.orcaslicer_settings,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        moderation_reason=None,
    )
    return await _finish_created_preset(
        db=db,
        current_user=current_user,
        preset=preset,
        printer_ids=data.printer_ids,
    )


@router.patch("/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: int,
    data: PresetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Обновить пресет."""
    result = await db.execute(
        select(Preset).where(Preset.id == preset_id).with_for_update()
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    # Взвешенные пресеты нельзя редактировать (они автоматически обновляются системой)
    if preset.is_weighted:
        raise_error(403, ERR_WEIGHTED_PRESET_READONLY)

    # Обновляем только переданные поля
    update_data = data.model_dump(exclude_unset=True)
    printer_ids = update_data.pop("printer_ids", None)
    requested_official = update_data.pop("is_official", None)
    if requested_official is not None and requested_official != preset.is_official:
        raise_error(409, ERR_PRESET_OWNERSHIP_IMMUTABLE)

    requested_name = update_data.get("name")
    if requested_name is not None:
        if not is_allowed_orca_preset_name(requested_name, preset.name):
            raise_error(400, ERR_INVALID_FILENAME)

    explicit_structured_changes = {
        key: update_data[key]
        for key in (
            "extruder_temp",
            "bed_temp",
            "flow_rate",
            "fan_speed",
            "retraction_length",
            "retraction_speed",
        )
        if key in update_data
    }
    if "orcaslicer_settings" in update_data and update_data["orcaslicer_settings"] is not None:
        try:
            extracted_changes = extract_structured_filament_values(
                update_data["orcaslicer_settings"]
            )
        except ValueError:
            raise_error(422, ERR_INVALID_PRESET_SETTINGS)
        for key, value in extracted_changes.items():
            update_data.setdefault(key, value)

    if explicit_structured_changes:
        raw_settings = update_data.get("orcaslicer_settings", preset.orcaslicer_settings)
        update_data["orcaslicer_settings"] = apply_structured_filament_updates(
            raw_settings,
            explicit_structured_changes,
        )

    # Определяем filament_id: из update_data (если передан) или из preset
    # Для черновиков filament_id может быть None, и мы его обновляем через update_data
    target_filament_id = (
        update_data["filament_id"]
        if "filament_id" in update_data
        else preset.filament_id
    )
    target_active = update_data.get("active", preset.active)
    if target_active and target_filament_id is None:
        raise_error(400, ERR_PRESET_FILAMENT_REQUIRED)

    # Получаем filament для автомодерации (только если есть filament_id)
    filament = None
    if target_filament_id:
        filament_result = await db.execute(select(Filament).where(Filament.id == target_filament_id))
        filament = filament_result.scalar_one_or_none()
        if not filament:
            raise_error(404, ERR_FILAMENT_NOT_FOUND)

    if not await _can_update_preset(db, current_user, preset, filament):
        raise_error(403, ERR_NO_PERMISSION_EDIT_PRESET)

    # Сохраняем старое состояние для проверки активации черновика.
    # sync больше управляется в user_saved_presets, поэтому здесь
    # учитываем только переход черновика в активный пресет.
    was_draft = not preset.active or not preset.filament_id
    stored_draft_settings = (
        dict(preset.orcaslicer_settings)
        if was_draft and isinstance(preset.orcaslicer_settings, dict)
        else {}
    )

    for field, value in update_data.items():
        setattr(preset, field, value)

    if preset.is_official:
        preset.moderation_status = PresetModerationStatus.APPROVED
        preset.moderation_reason = None

    if preset.filament_id is not None:
        from app.services.spoolmanager_import_service import (
            link_imported_spools_to_preset,
        )

        await link_imported_spools_to_preset(db, preset)

    # Автоматическая модерация при обновлении (только для пользовательских пресетов с filament)
    if not preset.is_official and filament:
        moderation_status, moderation_reason = await moderate_preset(
            preset,
            filament,
            db,
            is_official=preset.is_official,
            allow_manual_review=False,
        )
        # Если пресет был одобрен, а теперь отклонён - меняем статус
        if moderation_status == PresetModerationStatus.REJECTED:
            preset.moderation_status = moderation_status
            preset.moderation_reason = _serialize_moderation_reason(moderation_reason)
            preset.active = False
        # Требуется ручная проверка — переводим в pending и сохраняем причину/флаги.
        elif moderation_status == PresetModerationStatus.PENDING:
            preset.moderation_status = PresetModerationStatus.PENDING
            preset.moderation_reason = _serialize_moderation_reason(moderation_reason)
        # Если пресет проходит проверку, а текущий статус не APPROVED
        # (например, PENDING после импорта из OrcaSlicer), переводим в APPROVED.
        elif moderation_status == PresetModerationStatus.APPROVED and preset.moderation_status != PresetModerationStatus.APPROVED:
            preset.moderation_status = moderation_status
            preset.moderation_reason = None

    published_now = bool(was_draft and preset.active and preset.filament_id)
    if published_now:
        from app.services.preset_publication import prepare_published_draft

        await prepare_published_draft(
            db,
            preset=preset,
            user_id=current_user.id,
            stored_settings=stored_draft_settings,
        )
        logger.info("Published reviewed Orca draft preset %s", preset.id)
    elif preset.active:
        from app.services.preset_publication import apply_managed_orca_identity

        apply_managed_orca_identity(preset)

    if published_now:
        from app.services.preset_funnel_metrics import record_preset_funnel_event

        record_preset_funnel_event(db, "important_field_confirmed")
        record_preset_funnel_event(db, "preset_published")

    # Обновляем связи с принтерами, если указаны
    if printer_ids is not None:
        # Удаляем старые связи
        delete_result = await db.execute(
            select(PresetPrinter).where(PresetPrinter.preset_id == preset_id)
        )
        old_links = delete_result.scalars().all()
        for link in old_links:
            await db.delete(link)

        # Создаём новые связи
        if printer_ids:
            for i, printer_id in enumerate(printer_ids):
                # Проверяем существование принтера
                printer_result = await db.execute(select(Printer).where(Printer.id == printer_id))
                printer = printer_result.scalar_one_or_none()
                if not printer:
                    continue  # Пропускаем несуществующие принтеры

                # Создаём связь
                preset_printer = PresetPrinter(
                    preset_id=preset.id,
                    printer_id=printer_id,
                    is_primary=(i == 0),  # Первый принтер - основной
                )
                db.add(preset_printer)

    # Record a version after the edit (no-op if settings unchanged).
    from app.models.preset_version import PresetVersionSource
    from app.services import preset_version_service
    await preset_version_service.record_version(
        db, preset, source=PresetVersionSource.WEB_EDIT, user_id=current_user.id
    )

    await db.commit()

    if preset.filament_id:
        # Создаем уведомления для пользователей, у которых сохранен этот пресет
        try:
            await notify_preset_updated(
                preset_id=preset.id,
                preset_name=preset.name,
                filament_id=preset.filament_id,
                db=db,
            )
        except Exception as e:
            logger.error(f"Failed to create notifications for preset {preset.id} update: {e}")

    # Загружаем принтеры для ответа
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.printer_links).selectinload(PresetPrinter.printer))
        .where(Preset.id == preset_id)
    )
    preset_with_printers = result.scalar_one()

    return PresetResponse.model_validate(preset_with_printers)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> None:
    """Удалить пресет."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    # Взвешенные пресеты нельзя удалять (они автоматически управляются системой)
    if preset.is_weighted:
        raise_error(403, ERR_WEIGHTED_PRESET_NO_DELETE)

    filament = await db.get(Filament, preset.filament_id) if preset.filament_id else None
    if not await _can_update_preset(db, current_user, preset, filament):
        raise_error(403, ERR_NO_PERMISSION_DELETE_PRESET)

    # Сохраняем данные перед удалением для уведомлений и обновления взвешенного пресета
    filament_id = preset.filament_id
    preset_name = preset.name
    preset_id_for_notification = preset.id

    await db.delete(preset)
    await db.commit()

    # Создаем уведомления для пользователей, у которых сохранен этот пресет
    try:
        await notify_preset_deleted(
            preset_id=preset_id_for_notification,
            preset_name=preset_name,
            filament_id=filament_id,
            db=db,
        )
    except Exception as e:
        logger.error(f"Failed to create notifications for preset {preset_id_for_notification} deletion: {e}")

@router.post("/{preset_id}/activate", response_model=PresetResponse)
async def activate_preset(
    preset_id: int,
    body: PresetActivateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PresetResponse:
    """Activate a draft preset by linking it to a filament."""

    result = await db.execute(
        select(Preset).where(Preset.id == preset_id).with_for_update()
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    if preset.active:
        raise_error(400, ERR_PRESET_ALREADY_ACTIVE)

    # Verify filament exists
    fil_result = await db.execute(select(Filament).where(Filament.id == body.filament_id))
    filament = fil_result.scalar_one_or_none()
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    if not await _can_update_preset(db, current_user, preset, filament):
        raise_error(403, ERR_PRESET_NOT_OWNER)
    stored_draft_settings = (
        dict(preset.orcaslicer_settings)
        if isinstance(preset.orcaslicer_settings, dict)
        else {}
    )
    preset.filament_id = body.filament_id
    if preset.is_official:
        moderation_status = PresetModerationStatus.APPROVED
        moderation_reason = None
    else:
        moderation_status, moderation_reason = await moderate_preset(
            preset,
            filament,
            db,
            is_official=False,
            allow_manual_review=False,
        )
    preset.moderation_status = moderation_status
    preset.moderation_reason = (
        _serialize_moderation_reason(moderation_reason)
        if moderation_status != PresetModerationStatus.APPROVED
        else None
    )
    preset.active = moderation_status != PresetModerationStatus.REJECTED
    if preset.active:
        from app.services.preset_publication import prepare_published_draft

        await prepare_published_draft(
            db,
            preset=preset,
            user_id=current_user.id,
            stored_settings=stored_draft_settings,
        )

        from app.services.spoolmanager_import_service import (
            link_imported_spools_to_preset,
        )

        await link_imported_spools_to_preset(db, preset)

        from app.services.preset_funnel_metrics import record_preset_funnel_event

        record_preset_funnel_event(db, "preset_published")

    from app.models.preset_version import PresetVersionSource
    from app.services import preset_version_service

    await preset_version_service.record_version(
        db,
        preset,
        source=PresetVersionSource.WEB_EDIT,
        user_id=current_user.id,
    )

    await db.commit()
    await db.refresh(preset)

    logger.info(
        f"Preset '{preset.name}' (id={preset.id}) activated by user {current_user.id}, "
        f"linked to filament {body.filament_id}"
    )

    return PresetResponse.model_validate(preset)


@router.get("/{preset_id}/export/orcaslicer.json")
async def export_preset_json(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_preset_read)],
    version_id: int | None = Query(None, ge=1),
) -> Response:
    """
    Экспортировать профиль в формате OrcaSlicer (.json).

    Returns:
        JSONResponse: JSON файл профиля OrcaSlicer
    """
    # A local Orca profile is captured once as a private review draft. It must
    # not return to Orca as a second managed copy before the user binds it to a
    # catalogue Filament and publishes it.
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.filament).selectinload(Filament.brand))
        .where(Preset.id == preset_id)
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    if not preset.active or not preset.filament:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    selected_version = None
    if version_id is not None:
        from app.services import preset_version_service

        selected_version = await preset_version_service.get_version(
            db, preset_id, version_id
        )
        if selected_version is None:
            raise_error(
                404,
                ERR_PRESET_VERSION_NOT_FOUND,
                params={"version_id": version_id},
            )
        if not await _can_update_preset(db, current_user, preset, preset.filament):
            if not preset_version_service.is_public_version(selected_version, preset):
                raise_error(
                    404,
                    ERR_PRESET_VERSION_NOT_FOUND,
                    params={"version_id": version_id},
                )

    structured_override = (
        selected_version.snapshot_structured if selected_version is not None else None
    )
    export_name = (
        structured_override.get("name")
        if isinstance(structured_override, dict)
        else preset.name
    ) or preset.name
    export_extruder_temp = (
        structured_override.get("extruder_temp", preset.extruder_temp)
        if isinstance(structured_override, dict)
        else preset.extruder_temp
    )

    # EXPORT-6 fix: валидация обязательных полей перед экспортом → HTTP 422
    missing_fields = []
    if not export_name:
        missing_fields.append("name")
    if not preset.filament.material_type:
        missing_fields.append("filament.material_type")
    if export_extruder_temp is None:
        missing_fields.append("nozzle_temperature")
    if missing_fields:
        raise_error(422, ERR_EXPORT_MISSING_FIELDS, params={"fields": ", ".join(missing_fields)})

    # Library scope запрашивающего: targeted/compatible-пресет сужается до
    # выбранных machine-профилей пользователя (RFC §3.3); unscoped — как раньше.
    from app.models.printer_profile import PrinterProfile
    from app.models.user_saved_preset import UserSavedPreset, UserSavedPresetTarget

    target_profiles: list[PrinterProfile] = []
    scope_result = await db.execute(
        select(UserSavedPreset)
        .options(
            selectinload(UserSavedPreset.targets)
            .selectinload(UserSavedPresetTarget.profile)
            .selectinload(PrinterProfile.printer)
        )
        .where(
            UserSavedPreset.user_id == current_user.id,
            UserSavedPreset.preset_id == preset_id,
        )
    )
    saved_row = scope_result.scalar_one_or_none()
    if saved_row is not None and saved_row.scope in ("targeted", "compatible"):
        target_profiles = [
            target.profile
            for target in saved_row.targets
            if target.profile is not None
            and target.profile.owner_user_id == current_user.id
            and target.profile.active
        ]

    # Экспортируем в JSON
    try:
        settings_override = (
            selected_version.snapshot_orcaslicer_settings
            if selected_version is not None
            else None
        )
        if not await _can_update_preset(db, current_user, preset, preset.filament):
            from app.services.preset_publication import public_orca_settings

            settings_override = public_orca_settings(
                settings_override
                if settings_override is not None
                else preset.orcaslicer_settings
            )
        profile_dict = await preset_to_orcaslicer_json(
            preset,
            preset.filament,
            db,
            target_profiles=target_profiles,
            settings_override=settings_override,
            structured_override=structured_override,
        )
    except Exception as e:
        logger.error(f"Error exporting preset {preset_id}: {str(e)}", exc_info=True)
        raise_error(500, ERR_EXPORT_PRESET_ERROR)

    # Возвращаем JSON файл
    # Формируем безопасное имя файла (только латиница и безопасные символы для HTTP заголовков)
    brand_name = preset.filament.brand.name if preset.filament.brand else "Generic"

    # Формируем имя файла: используем имя пресета (OrcaSlicer поддерживает кириллицу, пробелы, спецсимволы)
    # Примеры из OrcaSlicer: "TEST-2 ABS.json", "ABS @FilamentHub2.json", "ABS HTP.json"
    if export_name:
        filename = safe_download_stem(export_name, "preset") + ".json"
    else:
        # Fallback: Brand Material.json или просто Material.json
        filename_parts = []
        if brand_name:
            filename_parts.append(safe_download_stem(brand_name, "Generic"))
        if preset.filament.material_type:
            filename_parts.append(safe_download_stem(preset.filament.material_type, "material"))

        if filename_parts:
            filename = " ".join(filename_parts) + ".json"
        else:
            filename = "preset.json"

    # Ограничиваем длину имени файла
    if len(filename) > 200:
        # Обрезаем до 200 символов, стараясь не резать по середине слова
        filename = filename[:197].rsplit(" ", 1)[0] + ".json"

    return JSONResponse(
        content=profile_dict,
        media_type="application/json",
        headers={
            "Content-Disposition": attachment_content_disposition(filename),
        }
    )


@router.get("/{preset_id}/export/orcaslicer.info")
async def export_preset_info(
    preset_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_preset_read)],
) -> Response:
    """
    Экспортировать .info файл в формате INI для OrcaSlicer.

    Returns:
        Response: .info файл профиля OrcaSlicer (INI формат)
    """
    from fastapi.responses import PlainTextResponse

    # Получаем preset с filament и brand
    result = await db.execute(
        select(Preset)
        .options(selectinload(Preset.filament).selectinload(Filament.brand))
        .where(Preset.id == preset_id, Preset.active == True)
    )
    preset = result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_PRESET_NOT_FOUND)

    if not preset.filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # EXPORT-6 fix: валидация обязательных полей перед экспортом → HTTP 422
    missing_fields = []
    if not preset.name:
        missing_fields.append("name")
    if not preset.filament.material_type:
        missing_fields.append("filament.material_type")
    if missing_fields:
        raise_error(422, ERR_EXPORT_MISSING_FIELDS, params={"fields": ", ".join(missing_fields)})

    # Генерируем .info файл (INI формат)
    info_content = generate_profile_info(preset, preset.filament)

    # Возвращаем .info файл
    brand_name = preset.filament.brand.name if preset.filament.brand else "Generic"
    filename = f"{brand_name}_{preset.filament.material_type}_{preset.name}.info"
    filename = filename.replace(" ", "_").replace("/", "_")

    # RFC 5987: non-ASCII filenames need filename* with UTF-8 encoding;
    # plain filename= must be ASCII-safe (latin-1 encoding limit in HTTP headers).
    try:
        filename.encode("latin-1")
        disposition = f'attachment; filename="{filename}"'
    except UnicodeEncodeError:
        ascii_fallback = filename.encode("ascii", errors="replace").decode("ascii")
        utf8_encoded = quote(filename, safe="")
        disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{utf8_encoded}'

    return PlainTextResponse(
        content=info_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": disposition,
        }
    )


@router.get("/recommended/{filament_id}", response_model=RecommendedPresetResponse)
async def get_recommended_preset(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendedPresetResponse:
    """Получить взвешенный пресет для материала (weighted average всех пресетов)."""
    try:
        recommended_values = await get_recommended_preset_values(filament_id, db)
        return RecommendedPresetResponse(
            filament_id=filament_id,
            **recommended_values
        )
    except ValueError:
        raise_error(404, ERR_FILAMENT_NO_PRESETS)
