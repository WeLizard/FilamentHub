"""QR code endpoints."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_current_active_user_optional
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_BRAND_NOT_FOUND,
    ERR_FILAMENT_NOT_FOUND,
    ERR_OFFICIAL_PRESET_NOT_FOUND,
    ERR_QR_VERIFIED_ONLY,
    raise_error,
)
from app.db.session import get_db
from app.models.filament import Filament
from app.models.user import User
from app.schemas.filament import FilamentResponse
from app.schemas.preset import PresetResponse
from app.services.catalog_url_service import filament_public_path
from app.services.filament_analytics import event_country, record_filament_event
from app.services.filament_preset_summary import bucket_by_kind, summary_query
from app.services.qr_service import (
    ensure_filament_qr_code,
    generate_branded_qr_code_image,
    generate_branded_qr_code_svg,
    generate_qr_code_image,
    generate_qr_code_svg,
    get_qr_code_path,
)

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/{short_code}")
async def redirect_qr_scan(
    short_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User | None = Depends(get_current_active_user_optional),
) -> RedirectResponse:
    """
    Редирект на страницу материала по короткому коду QR-кода.

    Инкрементирует счетчик сканирований.
    """
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).options(selectinload(Filament.brand)).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Инкрементируем счетчик
    filament.scans_count += 1
    record_filament_event(
        db,
        filament_id=filament.id,
        event_type="qr_scan",
        country=event_country(request, current_user),
    )
    await db.commit()

    # Редирект на страницу материала
    return RedirectResponse(f"{filament_public_path(filament, filament.brand)}?qr=true", status_code=301)


@router.post("/{short_code}/scan")
async def handle_qr_scan(
    short_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User | None = Depends(get_current_active_user_optional),
) -> dict:
    """
    Регистрирует сканирование QR-кода и возвращает распознанный материал.

    Вместе с материалом возвращается ведущий публичный пресет: официальный,
    либо лучший community-вариант. Сохранение остаётся отдельным явным действием.
    """
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).options(selectinload(Filament.brand)).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    current_user_id = current_user.id if current_user else None

    # Recognition is read-only apart from the privacy-safe scan analytics.
    filament.scans_count += 1
    record_filament_event(
        db,
        filament_id=filament.id,
        event_type="qr_scan",
        country=event_country(request, current_user),
    )
    await db.commit()

    # Reuse the catalogue's public-visibility contract. QR intake deliberately
    # prefers official provenance, then the highest-rated community candidate.
    preset_result = await db.execute(summary_query([filament.id]))
    public_presets = list(preset_result.scalars())
    preset_bucket = bucket_by_kind(public_presets).get(filament.id, {})
    if "official" in preset_bucket:
        selected_preset = preset_bucket["official"]
        preset_type = "official"
    else:
        community_candidates = [
            preset
            for preset in public_presets
            if not preset.is_official and not preset.is_weighted
        ]
        selected_preset = max(
            community_candidates,
            key=lambda preset: (
                preset.rating is not None,
                preset.rating or 0,
                preset.updated_at,
            ),
            default=None,
        )
    if selected_preset is not None and not selected_preset.is_official:
        preset_type = "community"
    elif selected_preset is None:
        preset_type = None
    preset_saved = None
    preset_sync_enabled = None

    if current_user_id is not None and selected_preset is not None:
        from app.models.user_saved_preset import UserSavedPreset

        saved_result = await db.execute(
            select(UserSavedPreset).where(
                UserSavedPreset.user_id == current_user_id,
                UserSavedPreset.preset_id == selected_preset.id,
            )
        )
        saved_preset = saved_result.scalar_one_or_none()
        preset_saved = saved_preset is not None
        if saved_preset is not None:
            preset_sync_enabled = saved_preset.sync

    await db.refresh(filament)
    await db.refresh(filament, attribute_names=["brand"])

    filament_response = FilamentResponse.model_validate(filament).model_copy(
        update={
            "brand_name": filament.brand.name,
            "brand_slug": filament.brand.slug,
            "brand_verified": filament.brand.verified,
        }
    )
    return {
        "filament": filament_response,
        "preset_added": False,
        "preset_saved": preset_saved,
        "preset_sync_enabled": preset_sync_enabled,
        "preset_type": preset_type,
        "preset": PresetResponse.model_validate_public(selected_preset)
        if selected_preset
        else None,
    }


@router.get("/{short_code}/preset")
async def get_qr_preset(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Возвращает официальный пресет для материала по QR-коду.

    Формат: OrcaSlicer JSON профиль.
    """
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Находим официальный пресет
    from app.models.preset import Preset
    from app.services.orcaslicer_exporter import export_preset_to_orcaslicer

    preset_result = await db.execute(
        select(Preset).where(
            Preset.filament_id == filament.id,
            Preset.is_official == True,
            Preset.active == True
        ).order_by(Preset.created_at.desc())
        .limit(1)
    )
    preset = preset_result.scalar_one_or_none()

    if not preset:
        raise_error(404, ERR_OFFICIAL_PRESET_NOT_FOUND)

    # Экспортируем в формат OrcaSlicer
    preset_json = await export_preset_to_orcaslicer(preset, db)

    return preset_json


@router.get("/filaments/{filament_id}/qr-code")
async def get_filament_qr_code(
    filament_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    size: int = Query(300, ge=100, le=1200),
    branded: bool = Query(False),
) -> StreamingResponse:
    """
    Получить QR-код для материала.

    Если QR-код еще не существует - генерируется новый (для верифицированных брендов).

    `branded` отдаёт тот же код со знаком FilamentHub в середине. Код и ссылка
    не меняются: это другая отрисовка, а не другой код, поэтому напечатанное
    раньше продолжает работать.
    """
    # Получаем материал
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Если QR-кода нет - проверяем, можем ли его создать
    if not filament.qr_code:
        # Проверяем, верифицирован ли бренд
        from app.models.brand import Brand
        brand_result = await db.execute(select(Brand).where(Brand.id == filament.brand_id))
        brand = brand_result.scalar_one_or_none()

        if not brand or not brand.verified:
            raise_error(403, ERR_QR_VERIFIED_ONLY)

        # Генерируем QR-код (short code + изображения этикеток)
        await ensure_filament_qr_code(filament, db)
        await db.commit()

    if branded:
        # Заранее сохранённых картинок у брендированного варианта нет: его
        # выбирают редко и осознанно, при подготовке макета.
        branded_buffer = generate_branded_qr_code_image(filament.qr_code, size=size)
        return StreamingResponse(
            iter([branded_buffer.getvalue()]),
            media_type="image/png",
            headers={
                "Content-Disposition": (
                    f'inline; filename="qr-{filament.qr_code}-{size}x{size}-branded.png"'
                ),
                "Cache-Control": "public, max-age=3600",
            },
        )

    # Проверяем, есть ли сохраненное изображение нужного размера
    saved_path = get_qr_code_path(filament.qr_code, size)

    if saved_path:
        # Используем сохраненное изображение
        from fastapi.responses import FileResponse
        return FileResponse(
            str(saved_path),
            media_type='image/png',
            headers={
                'Cache-Control': 'public, max-age=31536000',  # Кэшируем на 1 год
            }
        )

    # Если сохраненного нет - генерируем на лету (fallback)
    qr_buffer = generate_qr_code_image(filament.qr_code, size=size)

    # Возвращаем напрямую через StreamingResponse
    return StreamingResponse(
        iter([qr_buffer.getvalue()]),
        media_type='image/png',
        headers={
            'Content-Disposition': f'inline; filename="qr-{filament.qr_code}-{size}x{size}.png"',
            'Cache-Control': 'public, max-age=3600',  # Кэшируем на 1 час
        }
    )


@router.get("/filaments/{filament_id}/qr-code/download")
async def download_filament_qr_code(
    filament_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    size: int = Query(600, ge=300, le=1200),
    image_format: Annotated[Literal["png", "svg"], Query(alias="format")] = "png",
    branded: bool = Query(False),
) -> StreamingResponse:
    """
    Скачать QR-код в высоком разрешении для печати.

    Размеры: 300x300, 600x600, 1200x1200px.

    `branded` отдаёт тот же код со знаком FilamentHub — в обоих форматах, потому
    что на упаковку уходит вектор, и вариант без него был бы бесполезен ровно
    там, ради чего затевался.
    """
    # Проверяем права доступа: код относится к подтверждённому бренду целиком,
    # поэтому скачать макет может любой его действующий представитель.
    from app.models.brand import Brand

    # Получаем материал
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    brand_result = await db.execute(select(Brand).where(Brand.id == filament.brand_id))
    brand = brand_result.scalar_one_or_none()

    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    from app.services.territorial_access import can_represent_brand

    if not await can_represent_brand(db, current_user, brand.id):
        raise_error(403, ERR_ACCESS_DENIED)

    if not filament.qr_code:
        if not brand.verified:
            raise_error(403, ERR_QR_VERIFIED_ONLY)
        # Download is itself a recovery path. Representatives do not need to
        # find and press the separate bulk-repair button before preparing a
        # label for a verified brand.
        await ensure_filament_qr_code(filament, db)
        await db.commit()

    # Вектор — для типографии: на упаковке код печатают каким угодно размером,
    # и растр под это пришлось бы отдавать в каждом.
    suffix = "-branded" if branded else ""
    if image_format == "svg":
        vector = (
            generate_branded_qr_code_svg(filament.qr_code)
            if branded
            else generate_qr_code_svg(filament.qr_code)
        )
        return StreamingResponse(
            iter([vector.getvalue()]),
            media_type='image/svg+xml',
            headers={
                'Content-Disposition': (
                    f'attachment; filename="qr-{filament.qr_code}{suffix}.svg"'
                ),
                'Cache-Control': 'public, max-age=3600',
            }
        )

    # Заранее сохранённые картинки есть только у обычного варианта.
    saved_path = None if branded else get_qr_code_path(filament.qr_code, size)

    if saved_path:
        # Используем сохраненное изображение
        from fastapi.responses import FileResponse
        return FileResponse(
            str(saved_path),
            media_type='image/png',
            headers={
                'Content-Disposition': f'attachment; filename="qr-{filament.qr_code}-{size}x{size}.png"',
                'Cache-Control': 'public, max-age=31536000',
            }
        )

    # Если сохраненного нет - генерируем на лету (fallback)
    qr_buffer = (
        generate_branded_qr_code_image(filament.qr_code, size=size)
        if branded
        else generate_qr_code_image(filament.qr_code, size=size)
    )

    # Возвращаем напрямую через StreamingResponse с заголовком для скачивания
    return StreamingResponse(
        iter([qr_buffer.getvalue()]),
        media_type='image/png',
        headers={
            'Content-Disposition': (
                f'attachment; filename="qr-{filament.qr_code}-{size}x{size}{suffix}.png"'
            ),
            'Cache-Control': 'public, max-age=3600',
        }
    )
