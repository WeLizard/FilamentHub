"""QR code endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, get_current_active_user_optional
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_BRAND_NOT_FOUND,
    ERR_FILAMENT_NOT_FOUND,
    ERR_OFFICIAL_PRESET_NOT_FOUND,
    ERR_QR_NOT_FOUND,
    ERR_QR_VERIFIED_ONLY,
    raise_error,
)
from app.db.session import get_db
from app.models.filament import Filament
from app.models.user import User
from app.schemas.filament import FilamentResponse
from app.services.qr_service import (
    ensure_filament_qr_code,
    generate_qr_code_image,
    get_qr_code_path,
)

router = APIRouter(prefix="/qr", tags=["qr"])


@router.get("/{short_code}")
async def redirect_qr_scan(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse:
    """
    Редирект на страницу материала по короткому коду QR-кода.

    Инкрементирует счетчик сканирований.
    """
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Инкрементируем счетчик
    filament.scans_count += 1
    await db.commit()

    # Редирект на страницу материала
    return RedirectResponse(f"/filaments/{filament.id}?qr=true")


@router.post("/{short_code}/scan")
async def handle_qr_scan(
    short_code: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: User | None = Depends(get_current_active_user_optional),
) -> dict:
    """
    Регистрирует сканирование QR-кода и автоматически добавляет официальный пресет в профиль пользователя.

    Если пользователь авторизован и есть официальный пресет - он автоматически добавляется.
    """
    # Получаем материал по короткому коду
    result = await db.execute(
        select(Filament).where(Filament.qr_code == short_code)
    )
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Инкрементируем счетчик
    filament.scans_count += 1

    preset_added = False
    official_preset = None

    # Если пользователь авторизован - автоматически добавляем официальный пресет
    if current_user:
        from app.models.preset import Preset
        from app.models.user_saved_preset import UserSavedPreset
        from app.schemas.preset import PresetResponse

        # Находим официальный пресет для материала
        preset_result = await db.execute(
            select(Preset).where(
                Preset.filament_id == filament.id,
                Preset.is_official == True,
                Preset.active == True
            ).order_by(Preset.created_at.desc())
            .limit(1)
        )
        official_preset = preset_result.scalar_one_or_none()

        if official_preset:
            # Проверяем, нет ли уже этого пресета в профиле пользователя
            existing = await db.execute(
                select(UserSavedPreset).where(
                    UserSavedPreset.user_id == current_user.id,
                    UserSavedPreset.preset_id == official_preset.id
                )
            )

            if not existing.scalar_one_or_none():
                # Добавляем пресет в профиль пользователя
                saved_preset = UserSavedPreset(
                    user_id=current_user.id,
                    preset_id=official_preset.id,
                )
                db.add(saved_preset)
                official_preset.usage_count += 1
                preset_added = True

    await db.commit()
    await db.refresh(filament)
    # reload after commit: usage_count write expires attrs, model_validate would lazy-load
    if official_preset is not None:
        await db.refresh(official_preset)

    return {
        'filament': FilamentResponse.model_validate(filament),
        'preset_added': preset_added,
        'preset': PresetResponse.model_validate(official_preset) if official_preset else None
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
) -> StreamingResponse:
    """
    Получить QR-код для материала.

    Если QR-код еще не существует - генерируется новый (для верифицированных брендов).
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
) -> StreamingResponse:
    """
    Скачать QR-код в высоком разрешении для печати.

    Размеры: 300x300, 600x600, 1200x1200px.
    """
    # Проверяем права доступа (только владелец бренда)
    from app.models.brand import Brand

    # Получаем материал
    result = await db.execute(select(Filament).where(Filament.id == filament_id))
    filament = result.scalar_one_or_none()

    if not filament:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)

    # Проверяем права (только владелец бренда или админ)
    brand_result = await db.execute(select(Brand).where(Brand.id == filament.brand_id))
    brand = brand_result.scalar_one_or_none()

    if not brand:
        raise_error(404, ERR_BRAND_NOT_FOUND)

    from app.services.organization_access import can_edit_brand_catalog

    if not await can_edit_brand_catalog(db, current_user, brand.id):
        raise_error(403, ERR_ACCESS_DENIED)

    if not filament.qr_code:
        raise_error(404, ERR_QR_NOT_FOUND)

    # Проверяем, есть ли сохраненное изображение нужного размера
    saved_path = get_qr_code_path(filament.qr_code, size)

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
    qr_buffer = generate_qr_code_image(filament.qr_code, size=size)

    # Возвращаем напрямую через StreamingResponse с заголовком для скачивания
    return StreamingResponse(
        iter([qr_buffer.getvalue()]),
        media_type='image/png',
        headers={
            'Content-Disposition': f'attachment; filename="qr-{filament.qr_code}-{size}x{size}.png"',
            'Cache-Control': 'public, max-age=3600',
        }
    )
