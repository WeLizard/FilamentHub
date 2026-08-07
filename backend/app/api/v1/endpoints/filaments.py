"""Filament endpoints."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_CUSTOM_FILLER_VERIFIED_ONLY,
    ERR_CUSTOM_MATERIAL_FEATURE_VERIFIED_ONLY,
    ERR_FILAMENT_ALREADY_EXISTS,
    ERR_FILAMENT_HAS_CONTRIBUTIONS,
    ERR_FILAMENT_LINE_INVALID,
    ERR_FILAMENT_NOT_FOUND,
    ERR_NO_PERMISSION_DELETE_FILAMENT,
    ERR_NO_PERMISSION_EDIT_FILAMENT,
    raise_error,
)
from app.core.utils import escape_like, like_pattern
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament, FilamentAvailability
from app.models.filament_line import FilamentLine
from app.models.filament_review import FilamentReview
from app.models.preset import Preset
from app.models.printer import Printer
from app.models.user import User, UserRole
from app.schemas.filament import (
    KNOWN_ADDITIVES,
    KNOWN_FILLERS,
    KNOWN_PROPERTY_CLAIMS,
    FilamentCreate,
    FilamentListResponse,
    FilamentResponse,
    FilamentUpdate,
    normalize_ral_code,
)
from app.services.filament_preset_summary import (
    bucket_by_kind,
    summaries_for,
    summary_query,
)
from app.services.organization_access import can_edit_brand_catalog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/filaments", tags=["filaments"])


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_hex(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


async def _validate_custom_filler(
    visual_settings: object,
    brand: Brand | None,
    current_user: User,
    db: AsyncSession,
) -> None:
    """Кастомный наполнитель (вне KNOWN_FILLERS) разрешён только верифицированному
    бренду и проходит текстовую модерацию; неверифицированный — только известные."""
    if not visual_settings:
        return
    filler = getattr(visual_settings, "filler", None) or "none"
    if filler in KNOWN_FILLERS:
        return
    if current_user.role != UserRole.ADMIN and not (brand and brand.verified):
        raise_error(403, ERR_CUSTOM_FILLER_VERIFIED_ONLY)
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(filler, db, "filler")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)


async def _validate_material_features(
    visual_settings: object,
    additives: list[object] | None,
    property_claims: list[object] | None,
    brand: Brand | None,
    current_user: User,
    db: AsyncSession,
) -> None:
    """Validate custom visual, composition and property codes as one contract."""
    custom_values: list[tuple[str, str]] = []
    has_custom_visual = False

    if visual_settings:
        effects = getattr(visual_settings, "effects", None) or []
        filler = getattr(visual_settings, "filler", None) or "none"
        for effect in dict.fromkeys([filler, *effects]):
            if effect != "none" and effect not in KNOWN_FILLERS:
                custom_values.append((effect, "visual_effect"))
                has_custom_visual = True

    for additive in additives or []:
        code = getattr(additive, "code", None)
        if code and code not in KNOWN_ADDITIVES:
            custom_values.append((code, "filament_additive"))

    for claim in property_claims or []:
        code = getattr(claim, "code", None)
        if code and code not in KNOWN_PROPERTY_CLAIMS:
            custom_values.append((code, "filament_property"))

    if not custom_values:
        return
    if current_user.role != UserRole.ADMIN and not (brand and brand.verified):
        raise_error(
            403,
            ERR_CUSTOM_FILLER_VERIFIED_ONLY
            if has_custom_visual
            else ERR_CUSTOM_MATERIAL_FEATURE_VERIFIED_ONLY,
        )

    from app.services.preset_moderation import validate_text_field

    for value, field_name in dict.fromkeys(custom_values):
        is_valid, error_msg = await validate_text_field(value, db, field_name)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)


def _same_filament_color(
    existing_color_name: str | None,
    existing_color_hex: str | None,
    new_color_name: str | None,
    new_color_hex: str | None,
) -> bool:
    # Цвет — часть идентичности материала.
    # Приоритет: текстовое имя цвета; HEX используется только когда name отсутствует с обеих сторон.
    existing_name = _normalize_text(existing_color_name)
    incoming_name = _normalize_text(new_color_name)
    if existing_name or incoming_name:
        return existing_name == incoming_name

    existing_hex = _normalize_hex(existing_color_hex)
    incoming_hex = _normalize_hex(new_color_hex)
    if existing_hex or incoming_hex:
        return existing_hex == incoming_hex

    return True


@router.get("/", response_model=FilamentListResponse)
async def list_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    active_only: bool = Query(True),
    brand_id: int | None = Query(None),
    material_type: str | None = Query(None),
    printer_id: int | None = Query(None, gt=0),
    search: str | None = Query(
        None,
        description="Поиск по материалу, бренду, типу, цвету, составу, эффекту или свойству",
    ),
) -> FilamentListResponse:
    """Получить список материалов.

    `printer_id` не сужает витрину: материалы, у которых есть пресет под этот
    принтер, поднимаются наверх и перечисляются в `printer_matched_ids`.
    """
    # Build query
    query = select(Filament).options(selectinload(Filament.brand), selectinload(Filament.line))
    if active_only:
        query = query.where(Filament.active == True)
    if brand_id:
        query = query.where(Filament.brand_id == brand_id)
    if material_type:
        query = query.where(Filament.material_type == material_type)
    normalized_search = search.strip() if search else None
    if normalized_search:
        search_term = like_pattern(normalized_search)
        ral_search_term = like_pattern(str(normalize_ral_code(normalized_search)))
        query = query.outerjoin(Brand).where(
            or_(
                Filament.name.ilike(search_term),
                Brand.name.ilike(search_term),
                Filament.material_type.ilike(search_term),
                Filament.color_name.ilike(search_term),
                Filament.ral_code.ilike(ral_search_term),
                Filament.visual_settings["filler"].as_string().ilike(search_term),
                Filament.visual_settings["effects"].as_string().ilike(search_term),
                cast(Filament.additives, String).ilike(search_term),
                cast(Filament.property_claims, String).ilike(search_term),
            )
        )

    # Count total
    count_query = select(func.count()).select_from(Filament)
    if active_only:
        count_query = count_query.where(Filament.active == True)
    if brand_id:
        count_query = count_query.where(Filament.brand_id == brand_id)
    if material_type:
        count_query = count_query.where(Filament.material_type == material_type)
    if normalized_search:
        search_term = like_pattern(normalized_search)
        ral_search_term = like_pattern(str(normalize_ral_code(normalized_search)))
        count_query = count_query.outerjoin(Brand).where(
            or_(
                Filament.name.ilike(search_term),
                Brand.name.ilike(search_term),
                Filament.material_type.ilike(search_term),
                Filament.color_name.ilike(search_term),
                Filament.ral_code.ilike(ral_search_term),
                Filament.visual_settings["filler"].as_string().ilike(search_term),
                Filament.visual_settings["effects"].as_string().ilike(search_term),
                cast(Filament.additives, String).ilike(search_term),
                cast(Filament.property_claims, String).ilike(search_term),
            )
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    if printer_id is not None:
        from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
        from app.models.preset_printer import PresetPrinter

        fits_printer = (
            select(1)
            .select_from(Preset)
            .join(PresetPrinter, PresetPrinter.preset_id == Preset.id)
            .where(
                Preset.filament_id == Filament.id,
                PresetPrinter.printer_id == printer_id,
                Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
            )
            .exists()
        )
        query = query.order_by(fits_printer.desc(), Filament.name)
    else:
        query = query.order_by(Filament.name)
    query = query.offset(offset).limit(size)

    # Execute
    result = await db.execute(query)
    filaments = result.scalars().all()
    filament_ids = [filament.id for filament in filaments]

    pages = (total + size - 1) // size if total > 0 else 0

    printer_matched_ids: list[int] = []
    if printer_id is not None and filament_ids:
        from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
        from app.models.preset_printer import PresetPrinter

        matched_rows = await db.execute(
            select(Preset.filament_id)
            .join(PresetPrinter, PresetPrinter.preset_id == Preset.id)
            .where(
                Preset.filament_id.in_(filament_ids),
                PresetPrinter.printer_id == printer_id,
                Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
            )
            .distinct()
        )
        printer_matched_ids = sorted({row[0] for row in matched_rows if row[0] is not None})

    preset_stats: dict[int, dict[str, int]] = {}
    preset_summary_map: dict[int, dict[str, object]] = {}

    if filament_ids:
        from app.models.preset import PUBLIC_PRESET_STATUSES, Preset, PresetModerationStatus

        stats_query = (
            select(
                Preset.filament_id,
                func.count().label("total"),
                func.sum(case((Preset.is_official.is_(True), 1), else_=0)).label("official_count"),
                func.sum(case((Preset.is_official.is_(False), 1), else_=0)).label("community_count"),
            )
            .where(
                Preset.filament_id.in_(filament_ids),
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
            .group_by(Preset.filament_id)
        )
        stats_rows = await db.execute(stats_query)
        for row in stats_rows:
            preset_stats[row.filament_id] = {
                "total": int(row.total or 0),
                "official": int(row.official_count or 0),
                "community": int(row.community_count or 0),
            }

        presets = await db.execute(summary_query(filament_ids))
        preset_summary_map = bucket_by_kind(presets.scalars())

    # Serialize with brand_name and preset summary
    filament_responses = []
    for filament in filaments:
        filament_dict = FilamentResponse.model_validate(filament).model_dump()
        filament_dict["brand_name"] = filament.brand.name if filament.brand else None
        filament_dict["brand_slug"] = filament.brand.slug if filament.brand else None
        filament_dict["brand_verified"] = filament.brand.verified if filament.brand else False
        filament_dict["line_name"] = filament.line.name if filament.line else None
        filament_dict["currency"] = filament.brand.currency if filament.brand else "RUB"
        filament_dict["price_hidden"] = filament.brand.price_hidden if filament.brand else False

        stats = preset_stats.get(filament.id)
        if stats:
            filament_dict["presets_count"] = stats["total"]
            filament_dict["official_presets_count"] = stats["official"]
            filament_dict["community_presets_count"] = stats["community"]
        else:
            filament_dict["presets_count"] = 0
            filament_dict["official_presets_count"] = 0
            filament_dict["community_presets_count"] = 0

        official, summaries = summaries_for(preset_summary_map.get(filament.id, {}))
        filament_dict["official_preset"] = official
        filament_dict["preset_summaries"] = summaries

        filament_responses.append(filament_dict)

    return FilamentListResponse(
        items=filament_responses,
        total=total,
        page=page,
        size=size,
        pages=pages,
        printer_matched_ids=printer_matched_ids,
    )


@router.get("/material-types")
async def get_material_types(
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: bool = Query(True),
) -> list[str]:
    """
    Получить список уникальных типов материалов.

    Возвращает типы из material_mappings (начальные типы из миграций) +
    типы из активных филаментов (если есть).
    """
    from app.models.material_mapping import MaterialMapping

    # Получаем типы из material_mappings (начальные типы, заполненные миграцией)
    mapping_query = select(MaterialMapping.material_type).distinct()
    if active_only:
        mapping_query = mapping_query.where(MaterialMapping.active == True)
    mapping_query = mapping_query.order_by(MaterialMapping.material_type)

    mapping_result = await db.execute(mapping_query)
    mapping_types = {row[0] for row in mapping_result.all() if row[0]}

    # Получаем типы из активных филаментов (если есть дополнительные)
    filament_query = select(Filament.material_type).distinct()
    if active_only:
        filament_query = filament_query.where(Filament.active == True)
    filament_query = filament_query.order_by(Filament.material_type)

    filament_result = await db.execute(filament_query)
    filament_types = {row[0] for row in filament_result.all() if row[0]}

    # Объединяем оба множества (уникальные типы)
    all_material_types = sorted(mapping_types | filament_types)

    return all_material_types


@router.get("/{filament_id}", response_model=FilamentResponse)
async def get_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FilamentResponse:
    """Получить материал по ID."""
    result = await db.execute(
        select(Filament).options(selectinload(Filament.brand), selectinload(Filament.line)).where(Filament.id == filament_id)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    filament_dict = FilamentResponse.model_validate(filament).model_dump()
    filament_dict["brand_name"] = filament.brand.name if filament.brand else None
    filament_dict["line_name"] = filament.line.name if filament.line else None
    filament_dict["currency"] = filament.brand.currency if filament.brand else "RUB"
    filament_dict["price_hidden"] = filament.brand.price_hidden if filament.brand else False

    # The same three presets the catalogue card leads with. Until now the page
    # worked this out for itself from whichever presets happened to be on the
    # first page, which could miss the one it was looking for.
    summaries = await db.execute(summary_query([filament_id]))
    official, carousel = summaries_for(bucket_by_kind(summaries.scalars()).get(filament_id, {}))
    filament_dict["official_preset"] = official
    filament_dict["preset_summaries"] = carousel
    return filament_dict


@router.get("/{filament_id}/presets")
async def get_filament_presets(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    is_official: bool | None = Query(None),
    sort: Literal["best", "new"] = Query("best"),
    printer_id: int | None = Query(None, ge=1),
) -> dict:
    """Получить пресеты для материала.

    ``sort`` меняет только порядок: ``best`` — как в каталоге (официальные,
    затем по оценке), ``new`` — сначала недавние, чтобы свежий пресет под
    только что вышедший принтер не оставался под старыми с высокой оценкой.
    ``printer_id`` оставляет только пресеты, связанные с этой моделью принтера.
    """
    from app.models.preset import Preset
    from app.schemas.preset import PresetResponse

    # Check if filament exists
    filament_result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = filament_result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Build query - показываем только активные пресеты (все пресеты автоматически одобрены)
    from app.models.preset import PUBLIC_PRESET_STATUSES
    from app.models.preset_printer import PresetPrinter
    from app.schemas.printer import PrinterResponse

    query = select(Preset).options(
        selectinload(Preset.printer_links).selectinload(PresetPrinter.printer)
    ).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES)  # виден = публичные статусы
    )
    if is_official is not None:
        query = query.where(Preset.is_official == is_official)

    # Count total
    count_query = select(func.count()).select_from(Preset).where(
        Preset.filament_id == filament_id,
        Preset.active == True,
        Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES)
    )
    if is_official is not None:
        count_query = count_query.where(Preset.is_official == is_official)

    if printer_id is not None:
        linked_presets = (
            select(PresetPrinter.preset_id)
            .where(PresetPrinter.printer_id == printer_id)
            .scalar_subquery()
        )
        query = query.where(Preset.id.in_(linked_presets))
        count_query = count_query.where(Preset.id.in_(linked_presets))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate. The id decides ties: without it two presets sharing a rating and
    # a creation moment could swap places between pages, so scrolling would show
    # one twice and never show the other.
    if sort == "new":
        ordering = (Preset.created_at.desc(), Preset.id.desc())
    else:
        ordering = (
            Preset.is_official.desc(),
            Preset.rating.desc().nulls_last(),
            Preset.created_at.desc(),
            Preset.id.desc(),
        )

    offset = (page - 1) * size
    query = query.order_by(*ordering).offset(offset).limit(size)

    # Execute
    result = await db.execute(query)
    presets = result.scalars().unique().all()

    # Преобразуем пресеты в ответ с принтерами
    preset_items = []
    for preset in presets:
        try:
            preset_dict = PresetResponse.model_validate(preset).model_dump()
            preset_dict["printers"] = [
                PrinterResponse.model_validate(link.printer).model_dump()
                for link in preset.printer_links
            ]
            preset_items.append(preset_dict)
        except Exception as e:
            logger.error(f"Error serializing preset {preset.id}: {e}", exc_info=True)
            # Пропускаем проблемный пресет, но продолжаем обработку остальных
            continue

    pages = (total + size - 1) // size if total > 0 else 0

    return {
        "items": preset_items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.post("/", response_model=FilamentResponse, status_code=201)
async def create_filament(
    data: FilamentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentResponse:
    """Создать материал."""
    # Check if brand exists
    from app.models.material_mapping import MaterialMappingPriority
    from app.services.material_mapping_service import (
        create_material_mapping,
        get_material_preset,
    )

    brand_result = await db.execute(select(Brand).where(Brand.id == data.brand_id))
    brand = brand_result.scalar_one_or_none()
    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    # FilamentHub is an open catalog: authenticated community members may add a
    # missing filament whether or not the brand already has a verified owner.
    # Verification controls official brand management, not catalog contribution.

    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.name, db, "filament_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "filament_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if data.color_name:
        is_valid, error_msg = await validate_text_field(data.color_name, db, "color_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    await _validate_material_features(
        data.visual_settings,
        data.additives,
        data.property_claims,
        brand,
        current_user,
        db,
    )

    if data.line_id is not None:
        line = await db.scalar(select(FilamentLine).where(FilamentLine.id == data.line_id))
        if line is None or line.brand_id != data.brand_id:
            raise_error(400, ERR_FILAMENT_LINE_INVALID)

    normalized_name = data.name.strip()
    normalized_material_type = data.material_type.strip()
    normalized_color_name = data.color_name.strip() if data.color_name else None
    normalized_color_hex = data.color_hex.strip().upper() if data.color_hex else None

    duplicate_candidates_result = await db.execute(
        select(Filament)
        .where(
            Filament.brand_id == data.brand_id,
            Filament.active.is_(True),
            func.lower(func.trim(Filament.name)) == normalized_name.lower(),
            func.lower(func.trim(Filament.material_type)) == normalized_material_type.lower(),
        )
        .limit(20)
    )
    duplicate_candidates = duplicate_candidates_result.scalars().all()
    duplicate_filament = next(
        (
            candidate
            for candidate in duplicate_candidates
            if _same_filament_color(
                candidate.color_name,
                candidate.color_hex,
                normalized_color_name,
                normalized_color_hex,
            )
        ),
        None,
    )

    if duplicate_filament:
        raise_error(
            409,
            ERR_FILAMENT_ALREADY_EXISTS,
            {
                "filament_id": duplicate_filament.id,
                "filament_name": duplicate_filament.name,
                "brand_name": brand.name,
                "material_type": duplicate_filament.material_type,
                "color_name": duplicate_filament.color_name,
                "color_hex": duplicate_filament.color_hex,
                "ral_code": duplicate_filament.ral_code,
            },
        )

    # Generate unique slug from name
    from app.services.slug_service import generate_unique_slug
    slug = await generate_unique_slug(
        db=db,
        model=Filament,
        source=normalized_name,
        fallback="filament",
    )

    # Create filament
    filament_payload = data.model_dump()
    filament_payload["name"] = normalized_name
    filament_payload["material_type"] = normalized_material_type
    filament_payload["color_name"] = normalized_color_name
    filament_payload["color_hex"] = normalized_color_hex
    filament_payload["availability"] = FilamentAvailability(filament_payload["availability"])
    filament = Filament(**filament_payload, slug=slug)
    db.add(filament)
    await db.flush()  # Получаем ID без коммита

    # Если бренд верифицирован - автоматически генерируем QR-код
    if brand.verified:
        from app.services.qr_service import ensure_filament_qr_code

        await ensure_filament_qr_code(filament, db)

    await db.commit()
    await db.refresh(filament)

    # Автоматически создаём маппинг для нового типа материала, если его ещё нет
    material_type_upper = data.material_type.upper().strip()

    # Проверяем, есть ли уже маппинг для этого типа
    from app.models.material_mapping import MaterialMapping
    existing_mapping = await db.execute(
        select(MaterialMapping).where(
            MaterialMapping.material_type.ilike(escape_like(material_type_upper)),
            MaterialMapping.active == True,
        )
    )

    if not existing_mapping.scalar_one_or_none():
        # Маппинга нет - определяем базовый пресет через сервис
        base_preset = await get_material_preset(
            data.material_type,
            db,
            log_unknown=True,
        )

        # Создаём автоматический маппинг
        try:
            await create_material_mapping(
                material_type=data.material_type,
                orcaslicer_preset=base_preset,
                db=db,
                priority=MaterialMappingPriority.AUTOMATIC,
                brand_id=None,  # Автоматический маппинг, не от производителя
                description=f"Автоматически создан для материала '{data.material_type}' → '{base_preset}'",
            )
        except Exception as e:
            # Логируем ошибку, но не блокируем создание филамента
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to create automatic material mapping for '{data.material_type}': {e}"
            )

    return FilamentResponse.model_validate(filament)


@router.patch("/{filament_id}", response_model=FilamentResponse)
async def update_filament(
    filament_id: int,
    data: FilamentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FilamentResponse:
    """Обновить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Проверка прав доступа: только админ или сотрудник бренда может редактировать материалы
    if not await can_edit_brand_catalog(db, current_user, filament.brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    update_data = data.model_dump(exclude_unset=True)

    if "name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["name"], db, "filament_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if "description" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["description"], db, "filament_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if "color_name" in update_data:
        is_valid, error_msg = await validate_text_field(update_data["color_name"], db, "color_name")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if update_data.get("availability") is not None:
        update_data["availability"] = FilamentAvailability(update_data["availability"])

    if (
        data.visual_settings is not None
        or data.additives is not None
        or data.property_claims is not None
    ):
        brand_result = await db.execute(select(Brand).where(Brand.id == filament.brand_id))
        await _validate_material_features(
            data.visual_settings,
            data.additives,
            data.property_claims,
            brand_result.scalar_one_or_none(),
            current_user,
            db,
        )

    if update_data.get("line_id") is not None:
        line = await db.scalar(select(FilamentLine).where(FilamentLine.id == update_data["line_id"]))
        if line is None or line.brand_id != filament.brand_id:
            raise_error(400, ERR_FILAMENT_LINE_INVALID)

    # Update fields
    for field, value in update_data.items():
        setattr(filament, field, value)

    await db.commit()
    await db.refresh(filament)

    return FilamentResponse.model_validate(filament)


@router.delete("/{filament_id}", status_code=204)
async def delete_filament(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Удалить материал."""
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Проверка прав доступа: только админ или сотрудник бренда может удалять материалы
    if not await can_edit_brand_catalog(db, current_user, filament.brand_id):
        raise_error(403, ERR_NO_PERMISSION_DELETE_FILAMENT)

    # Удаление материала уносит с собой пресеты и отзывы: они привязаны к нему
    # каскадом. Сотрудник бренда не может потерять работу сообщества из-за
    # неопрятной карточки — ему остаётся снять её с витрины.
    if current_user.role != UserRole.ADMIN:
        # Пресеты удаляются по-настоящему, поэтому существующая строка — чья-то
        # работа, даже если она скрыта: черновик из слайсера ждёт проверки с тем
        # же снятым флагом, что и отклонённый пресет.
        preset_count = await db.scalar(
            select(func.count()).select_from(Preset).where(Preset.filament_id == filament_id)
        )
        # Отзыв удаляется мягко: строка остаётся, гаснет флаг. Держать карточку
        # ради отзыва, который автор сам убрал, значит защищать несуществующее.
        review_count = await db.scalar(
            select(func.count())
            .select_from(FilamentReview)
            .where(
                FilamentReview.filament_id == filament_id,
                FilamentReview.active.is_(True),
            )
        )
        if preset_count or review_count:
            raise_error(409, ERR_FILAMENT_HAS_CONTRIBUTIONS)

    await db.delete(filament)
    await db.commit()


@router.get("/{filament_id}/compatible-printers", response_model=list[dict])
async def get_compatible_printers(
    filament_id: int,
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> list[dict]:
    """
    Получить список принтеров, совместимых с филаментом.

    Использует VIEW filament_printer_compatibility_view для вывода совместимости
    на основе существующих связей через Preset и PrintProfile.
    """
    from sqlalchemy import text

    # Проверяем существование филамента
    filament = await db.get(Filament, filament_id)
    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Используем VIEW для получения совместимых принтеров
    query = text("""
        SELECT DISTINCT
            printer_id,
            printer_slug,
            printer_name,
            relation_source,
            MAX(confidence_score) as confidence_score
        FROM filament_printer_compatibility_view
        WHERE filament_id = :filament_id
          AND confidence_score >= :min_confidence
        GROUP BY printer_id, printer_slug, printer_name, relation_source
        ORDER BY confidence_score DESC, printer_name
    """)

    result = await db.execute(query, {"filament_id": filament_id, "min_confidence": min_confidence})
    rows = result.fetchall()

    # Получаем дополнительную информацию о принтерах
    printer_ids = [row[0] for row in rows]
    if not printer_ids:
        return []

    printers_query = select(Printer).where(Printer.id.in_(printer_ids))
    printers_result = await db.execute(printers_query)
    printers = {p.id: p for p in printers_result.scalars().all()}

    # Формируем ответ
    compatible_printers = []
    for row in rows:
        printer_id, printer_slug, printer_name, relation_source, confidence_score = row
        printer = printers.get(printer_id)
        if printer:
            compatible_printers.append({
                "id": printer.id,
                "slug": printer.slug,
                "name": printer.name,
                "manufacturer": printer.manufacturer,
                "relation_source": relation_source,
                "confidence_score": float(confidence_score),
            })

    return compatible_printers
