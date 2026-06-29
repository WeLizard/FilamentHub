"""Brand invitation endpoints — admin issues pre-verified invites, brands accept them."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_current_admin_user
from app.core.errors import (
    ERR_BRAND_INVITE_INVALID,
    ERR_BRAND_INVITE_NOT_FOUND,
    ERR_BRAND_SLUG_EXISTS,
    ERR_USER_ALREADY_IN_BRAND,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.user import User
from app.schemas.brand_invite import (
    BrandInviteAccept,
    BrandInviteAcceptResponse,
    BrandInviteAdminResponse,
    BrandInviteCreate,
    BrandInvitePublicResponse,
)
from app.services.email_service import send_brand_invite_email
from app.services.slug_service import generate_unique_slug

router = APIRouter(prefix="/brand-invites", tags=["brand-invites"])
admin_router = APIRouter(prefix="/admin/brand-invites", tags=["admin"])


def _invite_url(token: str) -> str:
    return f"{settings.BASE_URL}/brand-invite/{token}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_active(invite: BrandInvite) -> bool:
    if invite.accepted_at is not None:
        return False
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > _now()


# --- Public / brand-facing ---

@router.get("/{token}", response_model=BrandInvitePublicResponse)
async def get_brand_invite(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandInvitePublicResponse:
    """Проверить приглашение по токену (для страницы принятия)."""
    invite = await db.scalar(select(BrandInvite).where(BrandInvite.token == token))
    if invite is None:
        return BrandInvitePublicResponse(valid=False, reason=ERR_BRAND_INVITE_NOT_FOUND)
    if not _is_active(invite):
        return BrandInvitePublicResponse(
            valid=False, brand_name=invite.brand_name, email=invite.email,
            reason=ERR_BRAND_INVITE_INVALID,
        )
    return BrandInvitePublicResponse(valid=True, brand_name=invite.brand_name, email=invite.email)


@router.post("/{token}/accept", response_model=BrandInviteAcceptResponse)
async def accept_brand_invite(
    token: str,
    data: BrandInviteAccept,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> BrandInviteAcceptResponse:
    """Принять приглашение: создаётся верифицированный бренд и привязывается к пользователю."""
    invite = await db.scalar(select(BrandInvite).where(BrandInvite.token == token))
    if invite is None:
        raise_error(404, ERR_BRAND_INVITE_NOT_FOUND)
    if not _is_active(invite):
        raise_error(400, ERR_BRAND_INVITE_INVALID)
    if current_user.brand_id is not None:
        raise_error(400, ERR_USER_ALREADY_IN_BRAND)

    brand_name = data.brand_name.strip()
    slug = await generate_unique_slug(db=db, model=Brand, source=brand_name, fallback="brand")

    # Имя бренда уникально — если занято, сообщаем понятным кодом.
    existing = await db.scalar(select(Brand.id).where(Brand.name == brand_name))
    if existing is not None:
        raise_error(400, ERR_BRAND_SLUG_EXISTS)

    brand = Brand(name=brand_name, slug=slug, verified=bool(invite.pre_verified), active=True)
    db.add(brand)
    await db.flush()

    current_user.brand_id = brand.id
    invite.accepted_at = _now()
    invite.accepted_by_id = current_user.id
    await db.commit()
    await db.refresh(brand)

    return BrandInviteAcceptResponse(brand_id=brand.id, brand_name=brand.name)


# --- Admin ---

@admin_router.post("", response_model=BrandInviteAdminResponse, status_code=201)
async def create_brand_invite(
    data: BrandInviteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> BrandInviteAdminResponse:
    """Создать приглашение и отправить письмо на корпоративную почту бренда."""
    invite = BrandInvite(
        token=secrets.token_urlsafe(32),
        email=str(data.email).strip().lower(),
        brand_name=data.brand_name.strip() if data.brand_name else None,
        pre_verified=True,
        invited_by_id=admin.id,
        expires_at=_now() + timedelta(days=data.expires_days),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    url = _invite_url(invite.token)
    send_brand_invite_email(
        to=invite.email, brand_name=invite.brand_name, invite_url=url, site_url=settings.BASE_URL,
    )

    response = BrandInviteAdminResponse.model_validate(invite)
    response.invite_url = url
    return response


@admin_router.get("", response_model=list[BrandInviteAdminResponse])
async def list_brand_invites(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> list[BrandInviteAdminResponse]:
    """Список приглашений (новые сверху)."""
    result = await db.execute(select(BrandInvite).order_by(BrandInvite.created_at.desc()))
    invites = result.scalars().all()
    out: list[BrandInviteAdminResponse] = []
    for invite in invites:
        item = BrandInviteAdminResponse.model_validate(invite)
        item.invite_url = _invite_url(invite.token)
        out.append(item)
    return out


@admin_router.delete("/{invite_id}", status_code=204)
async def delete_brand_invite(
    invite_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> None:
    """Отозвать (удалить) приглашение."""
    invite = await db.scalar(select(BrandInvite).where(BrandInvite.id == invite_id))
    if invite is None:
        raise_error(404, ERR_BRAND_INVITE_NOT_FOUND)
    await db.delete(invite)
    await db.commit()
