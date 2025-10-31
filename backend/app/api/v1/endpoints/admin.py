"""Admin endpoints for moderation and verification."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin_user
from app.db.session import get_db
from app.models.brand import Brand
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User, UserRole
from app.schemas.brand import BrandResponse
from app.schemas.preset import PresetResponse
from app.schemas.user import UserResponse

router = APIRouter(prefix="/admin", tags=["admin"])


# ==================== Brand Verification ====================


@router.get("/brands/pending", response_model=list[BrandResponse])
async def list_pending_brands(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BrandResponse]:
    """Получить список брендов, ожидающих верификации."""
    result = await db.execute(
        select(Brand).where(Brand.verified == False, Brand.active == True).order_by(Brand.created_at)
    )
    brands = result.scalars().all()
    return [BrandResponse.model_validate(brand) for brand in brands]


@router.post("/brands/{brand_id}/verify", response_model=BrandResponse)
async def verify_brand(
    brand_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Верифицировать бренд (производителя)."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    
    brand.verified = True
    await db.commit()
    await db.refresh(brand)
    
    return BrandResponse.model_validate(brand)


@router.post("/brands/{brand_id}/unverify", response_model=BrandResponse)
async def unverify_brand(
    brand_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandResponse:
    """Отозвать верификацию бренда."""
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    
    if not brand:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand not found",
        )
    
    brand.verified = False
    await db.commit()
    await db.refresh(brand)
    
    return BrandResponse.model_validate(brand)


# ==================== Preset Moderation ====================


@router.get("/presets/pending", response_model=list[PresetResponse])
async def list_pending_presets(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
) -> list[PresetResponse]:
    """Получить список пресетов, ожидающих модерации."""
    offset = (page - 1) * size
    
    result = await db.execute(
        select(Preset)
        .where(
            Preset.moderation_status == PresetModerationStatus.PENDING,
            Preset.is_official == False,  # Только пользовательские
            Preset.active == True,
        )
        .order_by(Preset.created_at)
        .offset(offset)
        .limit(size)
    )
    presets = result.scalars().all()
    
    return [PresetResponse.model_validate(preset) for preset in presets]


@router.post("/presets/{preset_id}/approve", response_model=PresetResponse)
async def approve_preset(
    preset_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PresetResponse:
    """Одобрить пресет."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()
    
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )
    
    preset.moderation_status = PresetModerationStatus.APPROVED
    preset.moderated_by = admin.id
    preset.moderated_at = datetime.utcnow()
    preset.moderation_reason = None
    
    await db.commit()
    await db.refresh(preset)
    
    return PresetResponse.model_validate(preset)


@router.post("/presets/{preset_id}/reject", response_model=PresetResponse)
async def reject_preset(
    preset_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reason: str = Query(..., description="Причина отклонения"),
) -> PresetResponse:
    """Отклонить пресет с указанием причины."""
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    preset = result.scalar_one_or_none()
    
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preset not found",
        )
    
    preset.moderation_status = PresetModerationStatus.REJECTED
    preset.moderated_by = admin.id
    preset.moderated_at = datetime.utcnow()
    preset.moderation_reason = reason
    preset.active = False  # Отклоненные не показываем
    
    await db.commit()
    await db.refresh(preset)
    
    return PresetResponse.model_validate(preset)


# ==================== User Management ====================


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    role: UserRole | None = Query(None),
    active_only: bool = Query(True),
) -> list[UserResponse]:
    """Получить список пользователей."""
    query = select(User)
    
    if active_only:
        query = query.where(User.active == True)
    if role:
        query = query.where(User.role == role)
    
    offset = (page - 1) * size
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(size)
    )
    users = result.scalars().all()
    
    return [UserResponse.model_validate(user) for user in users]


@router.post("/users/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Активировать пользователя."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.active = True
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Деактивировать пользователя."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.active = False
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.post("/users/{user_id}/promote-admin", response_model=UserResponse)
async def promote_to_admin(
    user_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Назначить пользователя администратором."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    user.role = UserRole.ADMIN
    await db.commit()
    await db.refresh(user)
    
    return UserResponse.model_validate(user)


@router.get("/stats", response_model=dict)
async def get_admin_stats(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Получить статистику для админки."""
    # Users
    users_total = await db.scalar(select(func.count(User.id)))
    users_brands = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.BRAND))
    users_admins = await db.scalar(select(func.count(User.id)).where(User.role == UserRole.ADMIN))
    
    # Brands
    brands_total = await db.scalar(select(func.count(Brand.id)))
    brands_verified = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == True))
    brands_pending = await db.scalar(select(func.count(Brand.id)).where(Brand.verified == False))
    
    # Presets
    presets_total = await db.scalar(select(func.count(Preset.id)))
    presets_pending = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.PENDING)
    )
    presets_approved = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.APPROVED)
    )
    presets_rejected = await db.scalar(
        select(func.count(Preset.id)).where(Preset.moderation_status == PresetModerationStatus.REJECTED)
    )
    
    return {
        "users": {
            "total": users_total,
            "brands": users_brands,
            "admins": users_admins,
        },
        "brands": {
            "total": brands_total,
            "verified": brands_verified,
            "pending_verification": brands_pending,
        },
        "presets": {
            "total": presets_total,
            "pending_moderation": presets_pending,
            "approved": presets_approved,
            "rejected": presets_rejected,
        },
    }

