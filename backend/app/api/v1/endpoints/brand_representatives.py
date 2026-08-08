"""Официальные представители бренда по странам.

Модель и инварианты: .docs/domains/catalog/BRAND_TERRITORIAL_MODEL.md
"""

import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.brand_invites import (
    TERRITORY_PURPOSE,
    _deliver_invite,
    _invite_url,
    _is_active,
    _now,
)
from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_BRAND_NOT_FOUND,
    ERR_TEAM_INVITE_PENDING,
    raise_error,
)
from app.core.i18n import resolve_language
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.brand_territorial_grant import BrandTerritorialGrant, GrantStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.brand_team import (
    TerritoryInviteCreate,
    TerritoryInviteResponse,
    TerritoryResponse,
)
from app.services.territorial_access import can_invite_representative

router = APIRouter(prefix="/brands/{brand_id}/representatives", tags=["brand-representatives"])


def _invite_status(invite: BrandInvite) -> str:
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    if not _is_active(invite):
        return "expired"
    return invite.send_status if invite.send_status in {"sent", "failed"} else "pending"


def _invite_response(invite: BrandInvite) -> TerritoryInviteResponse:
    return TerritoryInviteResponse(
        id=invite.id,
        email=invite.email,
        country=invite.country or "",
        organization_name=invite.organization_name,
        brand_id=invite.brand_id,
        status=_invite_status(invite),
        invite_url=_invite_url(invite.token),
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        send_error=invite.send_error,
    )


async def _brand_for_representative_work(
    db: AsyncSession, brand_id: int, user: User
) -> Brand:
    brand = await db.get(Brand, brand_id)
    if brand is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
    if not await can_invite_representative(db, user, brand_id):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    return brand


@router.get("", response_model=list[TerritoryResponse])
async def list_representatives(
    brand_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TerritoryResponse]:
    """Кто ведёт бренд и в какой стране."""
    await _brand_for_representative_work(db, brand_id, current_user)

    rows = await db.execute(
        select(BrandTerritorialGrant, Organization.name)
        .join(Organization, Organization.id == BrandTerritorialGrant.organization_id)
        .where(
            BrandTerritorialGrant.brand_id == brand_id,
            BrandTerritorialGrant.status == GrantStatus.active,
            BrandTerritorialGrant.revoked_at.is_(None),
        )
        .order_by(BrandTerritorialGrant.country.is_(None).desc(), BrandTerritorialGrant.country)
    )
    return [
        TerritoryResponse(
            grant_id=grant.id,
            organization_id=grant.organization_id,
            organization_name=organization_name,
            country=grant.country,
            source=grant.source.value,
            approved_at=grant.approved_at,
        )
        for grant, organization_name in rows.all()
    ]


@router.post("/invites", response_model=TerritoryInviteResponse, status_code=201)
async def invite_representative(
    brand_id: int,
    data: TerritoryInviteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TerritoryInviteResponse:
    """Позвать компанию вести бренд в одной стране."""
    brand = await _brand_for_representative_work(db, brand_id, current_user)

    normalized_email = str(data.email).strip().casefold()
    pending = await db.scalar(
        select(BrandInvite)
        .where(
            BrandInvite.brand_id == brand.id,
            BrandInvite.email == normalized_email,
            BrandInvite.country == data.country,
            BrandInvite.purpose == TERRITORY_PURPOSE,
            BrandInvite.accepted_at.is_(None),
            BrandInvite.revoked_at.is_(None),
        )
        .order_by(BrandInvite.created_at.desc())
        .limit(1)
    )
    if pending is not None and _is_active(pending):
        raise_error(status.HTTP_409_CONFLICT, ERR_TEAM_INVITE_PENDING)

    invite = BrandInvite(
        token=secrets.token_urlsafe(32),
        email=normalized_email,
        brand_name=brand.name,
        target_type="existing",
        brand_id=brand.id,
        # Своя организация создаётся при принятии.
        organization_id=None,
        organization_name=data.organization_name.strip(),
        country=data.country,
        member_role="owner",
        purpose=TERRITORY_PURPOSE,
        all_brands=False,
        pre_verified=False,
        sender_profile="transactional",
        language=resolve_language(current_user.legal_acceptance_language),
        send_status="pending",
        reply_token=secrets.token_urlsafe(24),
        invited_by_id=current_user.id,
        expires_at=_now() + timedelta(days=data.expires_days),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    if data.send_email:
        await _deliver_invite(db, invite)
        await db.commit()
        await db.refresh(invite)
    return _invite_response(invite)


@router.delete("/{grant_id}", status_code=204)
async def revoke_representative(
    brand_id: int,
    grant_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Снять представительство."""
    await _brand_for_representative_work(db, brand_id, current_user)

    grant = await db.get(BrandTerritorialGrant, grant_id)
    if grant is None or grant.brand_id != brand_id:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)

    grant.status = GrantStatus.revoked
    grant.revoked_at = _now()
    await db.commit()
