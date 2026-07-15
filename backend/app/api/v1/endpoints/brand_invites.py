"""Brand invitation endpoints — admin issues pre-verified invites, brands accept them."""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_current_admin_user
from app.core.errors import (
    ERR_BRAND_INVITE_EMAIL_MISMATCH,
    ERR_BRAND_INVITE_INVALID,
    ERR_BRAND_INVITE_NOT_FOUND,
    ERR_BRAND_INVITE_TARGET_CONFLICT,
    ERR_BRAND_INVITE_TARGET_MISSING,
    ERR_BRAND_NOT_FOUND,
    ERR_ORGANIZATION_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole
from app.schemas.brand_invite import (
    BrandInviteAccept,
    BrandInviteAcceptResponse,
    BrandInviteAdminResponse,
    BrandInviteBatchCreate,
    BrandInviteCreate,
    BrandInvitePublicResponse,
)
from app.services.email_service import send_brand_invite_email, send_brand_team_invite_email
from app.services.qr_service import backfill_brand_qr_codes
from app.services.slug_service import generate_unique_slug

router = APIRouter(prefix="/brand-invites", tags=["brand-invites"])
admin_router = APIRouter(prefix="/admin/brand-invites", tags=["admin"])


def _invite_url(token: str) -> str:
    return f"{settings.BASE_URL}/brand-invite/{token}"


def _now() -> datetime:
    # Наивный UTC: колонки brand_invites — TIMESTAMP WITHOUT TIME ZONE (Postgres
    # отвергает aware-datetime в наивной колонке).
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_active(invite: BrandInvite) -> bool:
    if invite.accepted_at is not None or invite.revoked_at is not None:
        return False
    expires = invite.expires_at
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    return expires > _now()


def _mask_email(email: str) -> str:
    """Return a hint that is useful to the recipient without exposing the address."""
    local, separator, domain = email.partition("@")
    if not separator:
        return "***"
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def _email_domain(email: str) -> str:
    """Return a normalized domain for domain-bound manufacturer invites."""
    _, separator, domain = email.strip().casefold().rpartition("@")
    return domain.rstrip(".") if separator else ""


def _reply_to(invite: BrandInvite) -> str:
    if settings.EMAIL_INBOUND_DOMAIN and invite.reply_token:
        return f"invite-{invite.reply_token}@{settings.EMAIL_INBOUND_DOMAIN}"
    return settings.EMAIL_CONTACT


async def _resolve_invite_target(
    *,
    db: AsyncSession,
    target_type: str,
    brand_id: int | None,
    brand_name: str | None,
    organization_id: int | None,
) -> tuple[Brand | None, Organization | None, str, str | None]:
    """Validate an admin-authored target before an invitation is sent."""
    organization = None
    if organization_id is not None:
        organization = await db.get(Organization, organization_id)
        if organization is None or not organization.active:
            raise_error(404, ERR_ORGANIZATION_NOT_FOUND)

    if target_type == "existing":
        brand = await db.get(Brand, brand_id)
        if brand is None:
            raise_error(404, ERR_BRAND_NOT_FOUND)
        if organization and brand.organization_id not in (None, organization.id):
            raise_error(409, ERR_BRAND_INVITE_TARGET_CONFLICT, {"brand_id": brand.id})
        return brand, organization, brand.name, brand.slug

    normalized_name = (brand_name or "").strip()
    if not normalized_name:
        raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    duplicate = await db.scalar(
        select(Brand.id).where(func.lower(Brand.name) == normalized_name.casefold())
    )
    if duplicate is not None:
        raise_error(409, ERR_BRAND_INVITE_TARGET_CONFLICT, {"brand_id": duplicate})
    proposed_slug = await generate_unique_slug(
        db=db,
        model=Brand,
        source=normalized_name,
        fallback="brand",
    )
    return None, organization, normalized_name, proposed_slug


async def _build_invite(
    *,
    db: AsyncSession,
    email: str,
    target_type: str,
    brand_id: int | None,
    brand_name: str | None,
    organization_id: int | None,
    member_role: str,
    sender_profile: str,
    expires_days: int,
    admin_id: int,
    batch_id: str | None,
) -> BrandInvite:
    brand, organization, resolved_name, proposed_slug = await _resolve_invite_target(
        db=db,
        target_type=target_type,
        brand_id=brand_id,
        brand_name=brand_name,
        organization_id=organization_id,
    )
    invite = BrandInvite(
        token=secrets.token_urlsafe(32),
        email=email.strip().casefold(),
        brand_name=resolved_name,
        proposed_slug=proposed_slug,
        target_type=target_type,
        brand_id=brand.id if brand else None,
        organization_id=organization.id if organization else None,
        member_role=member_role,
        pre_verified=True,
        sender_profile=sender_profile,
        batch_id=batch_id,
        reply_token=secrets.token_urlsafe(24),
        invited_by_id=admin_id,
        expires_at=_now() + timedelta(days=expires_days),
    )
    db.add(invite)
    return invite


async def _deliver_invite(db: AsyncSession, invite: BrandInvite) -> None:
    # Legacy invitations created before inbound replies were introduced receive
    # a routing token on their next delivery/resend.
    if not invite.reply_token:
        invite.reply_token = secrets.token_urlsafe(24)

    if invite.purpose == "team":
        result = await run_in_threadpool(
            send_brand_team_invite_email,
            to=invite.email,
            brand_name=invite.brand_name or "FilamentHub",
            invite_url=_invite_url(invite.token),
            site_url=settings.BASE_URL,
            role=invite.member_role,
            reply_to=_reply_to(invite),
        )
    else:
        result = await run_in_threadpool(
            send_brand_invite_email,
            to=invite.email,
            brand_name=invite.brand_name,
            invite_url=_invite_url(invite.token),
            site_url=settings.BASE_URL,
            sender_profile=invite.sender_profile,
            reply_to=_reply_to(invite),
        )
    invite.send_status = "sent" if result.sent else "failed"
    invite.sent_at = _now() if result.sent else None
    invite.provider_message_id = result.provider_message_id
    invite.send_error = result.error[:500] if result.error else None


def _admin_response(invite: BrandInvite) -> BrandInviteAdminResponse:
    response = BrandInviteAdminResponse.model_validate(invite)
    response.invite_url = _invite_url(invite.token)
    return response


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
            valid=False,
            brand_name=invite.brand_name,
            email=_mask_email(invite.email),
            target_type=invite.target_type,
            brand_id=invite.brand_id,
            purpose=invite.purpose,
            member_role=invite.member_role,
            reason=ERR_BRAND_INVITE_INVALID,
        )
    return BrandInvitePublicResponse(
        valid=True,
        brand_name=invite.brand_name,
        email=_mask_email(invite.email),
        target_type=invite.target_type,
        brand_id=invite.brand_id,
        purpose=invite.purpose,
        member_role=invite.member_role,
    )


@router.post("/{token}/accept", response_model=BrandInviteAcceptResponse)
async def accept_brand_invite(
    token: str,
    data: BrandInviteAccept,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> BrandInviteAcceptResponse:
    """Accept an admin invitation and grant organization rights atomically."""
    invite = await db.scalar(
        select(BrandInvite).where(BrandInvite.token == token).with_for_update()
    )
    if invite is None:
        raise_error(404, ERR_BRAND_INVITE_NOT_FOUND)

    # A successful request may be retried after the response was interrupted.
    if invite.accepted_at is not None:
        if (
            invite.accepted_by_id == current_user.id
            and invite.brand_id is not None
            and invite.organization_id is not None
        ):
            accepted_brand = await db.get(Brand, invite.brand_id)
            if accepted_brand is not None:
                return BrandInviteAcceptResponse(
                    brand_id=accepted_brand.id,
                    brand_name=accepted_brand.name,
                    organization_id=invite.organization_id,
                    member_role=invite.member_role,
                )
        raise_error(400, ERR_BRAND_INVITE_INVALID)
    if not _is_active(invite):
        raise_error(400, ERR_BRAND_INVITE_INVALID)
    email_matches = (
        secrets.compare_digest(current_user.email.strip().casefold(), invite.email)
        if invite.purpose == "team"
        else secrets.compare_digest(
            _email_domain(current_user.email),
            _email_domain(invite.email),
        )
    )
    if not email_matches:
        raise_error(403, ERR_BRAND_INVITE_EMAIL_MISMATCH)

    # The invite target is authored by the admin and cannot be replaced by a
    # client-controlled value during acceptance.
    if not invite.brand_name or not invite.brand_name.strip():
        raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    brand = await db.get(Brand, invite.brand_id) if invite.brand_id else None
    if brand is None and invite.target_type == "existing":
        raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    if brand is None and invite.purpose == "team":
        raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    if brand is None:
        brand_name = invite.brand_name.strip()
        existing = await db.scalar(
            select(Brand.id).where(func.lower(Brand.name) == brand_name.casefold())
        )
        if existing is not None:
            raise_error(409, ERR_BRAND_INVITE_TARGET_CONFLICT, {"brand_id": existing})
        slug = await generate_unique_slug(
            db=db,
            model=Brand,
            source=invite.proposed_slug or brand_name,
            fallback="brand",
        )
        brand = Brand(name=brand_name, slug=slug, verified=False, active=True)
        db.add(brand)
        await db.flush()

    organization = (
        await db.get(Organization, invite.organization_id)
        if invite.organization_id is not None
        else None
    )
    if organization is None and brand.organization_id is not None:
        organization = await db.get(Organization, brand.organization_id)
    if organization is None and invite.purpose == "team":
        raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    if organization is None:
        organization_slug = await generate_unique_slug(
            db=db,
            model=Organization,
            source=brand.name,
            fallback="organization",
        )
        organization = Organization(
            name=brand.name,
            slug=organization_slug,
            created_by_id=current_user.id,
            active=True,
        )
        db.add(organization)
        await db.flush()
    else:
        locked_organization_id = await db.scalar(
            select(Organization.id)
            .where(Organization.id == organization.id, Organization.active.is_(True))
            .with_for_update()
        )
        if locked_organization_id is None:
            raise_error(400, ERR_BRAND_INVITE_TARGET_MISSING)
    if brand.organization_id not in (None, organization.id):
        raise_error(409, ERR_BRAND_INVITE_TARGET_CONFLICT, {"brand_id": brand.id})
    brand.organization_id = organization.id
    if invite.purpose != "team":
        if invite.pre_verified and not brand.verified:
            brand.name_correction_available = True
        brand.verified = brand.verified or bool(invite.pre_verified)
        await backfill_brand_qr_codes(brand, db)

    try:
        invited_role = OrganizationMemberRole(invite.member_role)
    except ValueError:
        invited_role = OrganizationMemberRole.OWNER
    membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == current_user.id,
        )
        .with_for_update()
    )
    role_rank = {
        OrganizationMemberRole.EDITOR: 0,
        OrganizationMemberRole.OWNER: 1,
    }
    invited_all_brands = (
        invited_role == OrganizationMemberRole.OWNER
        or (invite.purpose == "team" and invite.all_brands)
    )
    if membership is None:
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=current_user.id,
            role=invited_role,
            all_brands=invited_all_brands,
            active=True,
            invited_by_id=invite.invited_by_id,
        )
        db.add(membership)
        await db.flush()
    else:
        was_active = membership.active
        membership.active = True
        if not was_active:
            # A removed member must return with the role and scope from the new
            # invitation, not silently regain stale owner privileges.
            membership.role = invited_role
            membership.all_brands = invited_all_brands
            membership.invited_by_id = invite.invited_by_id
            await db.execute(
                delete(OrganizationBrandAccess).where(
                    OrganizationBrandAccess.membership_id == membership.id
                )
            )
        else:
            if role_rank[invited_role] > role_rank[membership.role]:
                membership.role = invited_role
            if membership.role == OrganizationMemberRole.OWNER:
                membership.all_brands = True
            elif invite.purpose == "team" and invite.all_brands:
                membership.all_brands = True
        if membership.all_brands:
            await db.execute(
                delete(OrganizationBrandAccess).where(
                    OrganizationBrandAccess.membership_id == membership.id
                )
            )

    if not membership.all_brands:
        access = await db.scalar(
            select(OrganizationBrandAccess).where(
                OrganizationBrandAccess.membership_id == membership.id,
                OrganizationBrandAccess.brand_id == brand.id,
            )
        )
        if access is None:
            db.add(OrganizationBrandAccess(membership_id=membership.id, brand_id=brand.id))

    # Transitional pointer used by the current single-brand profile UI. It is
    # the user's active brand, not the source of truth for authorization.
    current_user.brand_id = brand.id
    if current_user.role == UserRole.USER:
        current_user.role = UserRole.BRAND
    invite.brand_id = brand.id
    invite.organization_id = organization.id
    invite.accepted_at = _now()
    invite.accepted_by_id = current_user.id

    if invite.batch_id and invite.purpose != "team":
        await db.execute(
            update(BrandInvite)
            .where(
                BrandInvite.batch_id == invite.batch_id,
                BrandInvite.accepted_at.is_(None),
            )
            .values(brand_id=brand.id, organization_id=organization.id, target_type="existing")
        )
    await db.commit()
    await db.refresh(brand)

    return BrandInviteAcceptResponse(
        brand_id=brand.id,
        brand_name=brand.name,
        organization_id=organization.id,
        member_role=membership.role.value,
    )


# --- Admin ---

@admin_router.post("", response_model=BrandInviteAdminResponse, status_code=201)
async def create_brand_invite(
    data: BrandInviteCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> BrandInviteAdminResponse:
    """Create one independently trackable manufacturer invitation."""
    invite = await _build_invite(
        db=db,
        email=str(data.email),
        target_type=data.target_type,
        brand_id=data.brand_id,
        brand_name=data.brand_name,
        organization_id=data.organization_id,
        member_role=data.member_role,
        sender_profile=data.sender_profile,
        expires_days=data.expires_days,
        admin_id=admin.id,
        batch_id=None,
    )
    await db.flush()
    await db.commit()
    await db.refresh(invite)

    await _deliver_invite(db, invite)
    await db.commit()
    await db.refresh(invite)
    return _admin_response(invite)


@admin_router.post("/batch", response_model=list[BrandInviteAdminResponse], status_code=201)
async def create_brand_invite_batch(
    data: BrandInviteBatchCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> list[BrandInviteAdminResponse]:
    """Send one single-use token per normalized, de-duplicated recipient."""
    emails = list(dict.fromkeys(str(email).strip().casefold() for email in data.emails))
    batch_id = str(uuid.uuid4())
    invites: list[BrandInvite] = []
    for email in emails:
        invite = await _build_invite(
            db=db,
            email=email,
            target_type=data.target_type,
            brand_id=data.brand_id,
            brand_name=data.brand_name,
            organization_id=data.organization_id,
            member_role=data.member_role,
            sender_profile=data.sender_profile,
            expires_days=data.expires_days,
            admin_id=admin.id,
            batch_id=batch_id,
        )
        invites.append(invite)
    await db.flush()
    await db.commit()

    for invite in invites:
        await _deliver_invite(db, invite)
    await db.commit()
    for invite in invites:
        await db.refresh(invite)
    return [_admin_response(invite) for invite in invites]


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
        out.append(_admin_response(invite))
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
