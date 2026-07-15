"""Organization team management scoped through a public brand."""

import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.brand_invites import _deliver_invite, _invite_url, _is_active, _now
from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_BRAND_INVITE_NOT_FOUND,
    ERR_BRAND_NOT_FOUND,
    ERR_LAST_ORGANIZATION_OWNER,
    ERR_ORGANIZATION_MEMBERSHIP_NOT_FOUND,
    ERR_ORGANIZATION_NOT_FOUND,
    ERR_REQUEST_NOT_FOUND,
    ERR_REQUEST_NOT_PENDING,
    ERR_TEAM_INVITE_PENDING,
    ERR_USER_NOT_FOUND,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.brand_request import BrandRequest, BrandRequestStatus, BrandRequestType
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole
from app.schemas.brand_team import (
    BrandTeamWorkspaceResponse,
    OwnershipTransferRequest,
    TeamInviteCreate,
    TeamInviteResponse,
    TeamJoinRequestDecision,
    TeamJoinRequestResponse,
    TeamMemberResponse,
    TeamMembershipUpdate,
)
from app.services.notification_service import (
    notify_brand_request_approved,
    notify_brand_request_rejected,
)
from app.services.organization_access import get_brand_membership, grant_brand_editor_membership

router = APIRouter(prefix="/brands/{brand_id}/team", tags=["brand-team"])


async def _brand_workspace(
    db: AsyncSession,
    *,
    brand_id: int,
    user: User,
    owner_required: bool = False,
) -> tuple[Brand, Organization, OrganizationMembership | None]:
    brand = await db.get(Brand, brand_id)
    if brand is None or not brand.active:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_NOT_FOUND)
    if brand.organization_id is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_NOT_FOUND)
    organization = await db.get(Organization, brand.organization_id)
    if organization is None or not organization.active:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_NOT_FOUND)
    membership = await get_brand_membership(db, user, brand_id)
    is_site_admin = user.role == UserRole.ADMIN
    if membership is None and not is_site_admin:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    if (
        owner_required
        and not is_site_admin
        and (membership is None or membership.role != OrganizationMemberRole.OWNER)
    ):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    return brand, organization, membership


def _invite_status(invite: BrandInvite) -> str:
    if invite.revoked_at is not None:
        return "revoked"
    if invite.accepted_at is not None:
        return "accepted"
    if not _is_active(invite):
        return "expired"
    return invite.send_status


def _invite_response(invite: BrandInvite) -> TeamInviteResponse:
    return TeamInviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.member_role,
        all_brands=invite.all_brands,
        brand_id=invite.brand_id,
        status=_invite_status(invite),
        invite_url=_invite_url(invite.token),
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        send_error=invite.send_error,
    )


async def _other_owner_count(
    db: AsyncSession,
    *,
    organization_id: int,
    membership_id: int,
) -> int:
    return int(
        await db.scalar(
            select(func.count(OrganizationMembership.id)).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.active.is_(True),
                OrganizationMembership.role == OrganizationMemberRole.OWNER,
                OrganizationMembership.id != membership_id,
            )
        )
        or 0
    )


async def _lock_organization(db: AsyncSession, organization_id: int) -> None:
    """Serialize role/lifecycle changes inside one organization."""
    locked_id = await db.scalar(
        select(Organization.id)
        .where(Organization.id == organization_id, Organization.active.is_(True))
        .with_for_update()
    )
    if locked_id is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_NOT_FOUND)


async def _owner_workspace(
    db: AsyncSession,
    *,
    brand_id: int,
    user: User,
) -> tuple[Brand, Organization, OrganizationMembership | None]:
    """Lock an organization and revalidate the caller's owner role."""
    brand, organization, _ = await _brand_workspace(
        db,
        brand_id=brand_id,
        user=user,
        owner_required=True,
    )
    await _lock_organization(db, organization.id)
    if user.role == UserRole.ADMIN:
        return brand, organization, await get_brand_membership(db, user, brand_id)
    membership = await get_brand_membership(db, user, brand_id)
    if membership is None or membership.role != OrganizationMemberRole.OWNER:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    return brand, organization, membership


async def _replace_scope(
    db: AsyncSession,
    *,
    organization_id: int,
    membership: OrganizationMembership,
    role: OrganizationMemberRole,
    all_brands: bool,
    brand_ids: list[int],
) -> None:
    if role == OrganizationMemberRole.OWNER:
        all_brands = True
        brand_ids = []
    if not all_brands:
        valid_ids = set(
            (
                await db.scalars(
                    select(Brand.id).where(
                        Brand.organization_id == organization_id,
                        Brand.id.in_(brand_ids),
                        Brand.active.is_(True),
                    )
                )
            ).all()
        )
        if valid_ids != set(brand_ids):
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_BRAND_NOT_FOUND)

    membership.role = role
    membership.all_brands = all_brands
    await db.execute(
        delete(OrganizationBrandAccess).where(
            OrganizationBrandAccess.membership_id == membership.id
        )
    )
    if not all_brands:
        for scoped_brand_id in brand_ids:
            db.add(
                OrganizationBrandAccess(
                    membership_id=membership.id,
                    brand_id=scoped_brand_id,
                )
            )


@router.get("", response_model=BrandTeamWorkspaceResponse)
async def get_brand_team(
    brand_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BrandTeamWorkspaceResponse:
    """Return only the caller's organization; never enumerate site users."""
    brand, organization, current_membership = await _brand_workspace(
        db, brand_id=brand_id, user=current_user
    )
    is_site_admin = current_user.role == UserRole.ADMIN
    is_owner = (
        current_membership is not None
        and current_membership.role == OrganizationMemberRole.OWNER
    )
    can_manage_team = is_site_admin or is_owner
    member_query = (
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.active.is_(True),
            User.active.is_(True),
        )
        .order_by(OrganizationMembership.joined_at.asc())
    )
    if not can_manage_team:
        if current_membership is None:
            raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
        member_query = member_query.where(OrganizationMembership.id == current_membership.id)
    member_rows = (await db.execute(member_query)).all()
    membership_ids = [membership.id for membership, _ in member_rows]
    access_rows = (
        await db.execute(
            select(OrganizationBrandAccess.membership_id, OrganizationBrandAccess.brand_id).where(
                OrganizationBrandAccess.membership_id.in_(membership_ids)
            )
        )
        if membership_ids
        else None
    )
    access_by_membership: dict[int, list[int]] = {}
    if access_rows is not None:
        for membership_id, scoped_brand_id in access_rows.all():
            access_by_membership.setdefault(membership_id, []).append(scoped_brand_id)

    members = [
        TeamMemberResponse(
            membership_id=membership.id,
            user_id=member.id,
            username=member.username,
            email=member.email,
            role=membership.role.value,
            all_brands=membership.all_brands,
            brand_ids=sorted(access_by_membership.get(membership.id, [])),
            joined_at=membership.joined_at,
            is_current_user=member.id == current_user.id,
        )
        for membership, member in member_rows
    ]

    invites: list[TeamInviteResponse] = []
    join_requests: list[TeamJoinRequestResponse] = []
    if can_manage_team:
        invite_models = (
            await db.scalars(
                select(BrandInvite)
                .where(
                    BrandInvite.organization_id == organization.id,
                    BrandInvite.purpose == "team",
                )
                .order_by(BrandInvite.created_at.desc())
                .limit(100)
            )
        ).all()
        invites = [_invite_response(invite) for invite in invite_models]

        if brand.verified:
            request_rows = (
                await db.execute(
                    select(BrandRequest, User)
                    .join(User, User.id == BrandRequest.user_id)
                    .where(
                        BrandRequest.request_type == BrandRequestType.JOIN,
                        BrandRequest.brand_id == brand_id,
                        BrandRequest.status == BrandRequestStatus.PENDING,
                        User.active.is_(True),
                    )
                    .order_by(BrandRequest.created_at.asc())
                )
            ).all()
            join_requests = [
                TeamJoinRequestResponse(
                    id=request.id,
                    user_id=member.id,
                    username=member.username,
                    email=member.email,
                    message=request.message,
                    created_at=request.created_at,
                )
                for request, member in request_rows
            ]

    return BrandTeamWorkspaceResponse(
        organization_id=organization.id,
        organization_name=organization.name,
        current_role=(
            "admin"
            if is_site_admin
            else current_membership.role.value
        ),
        can_manage_team=can_manage_team,
        can_transfer_ownership=is_owner,
        members=members,
        pending_invites=invites,
        pending_join_requests=join_requests,
    )


@router.post("/invites", response_model=TeamInviteResponse, status_code=201)
async def create_team_invite(
    brand_id: int,
    data: TeamInviteCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TeamInviteResponse:
    brand, organization, _ = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    if not brand.verified:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    normalized_email = str(data.email).strip().casefold()
    pending = await db.scalar(
        select(BrandInvite)
        .where(
            BrandInvite.organization_id == organization.id,
            BrandInvite.email == normalized_email,
            BrandInvite.purpose == "team",
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
        organization_id=organization.id,
        member_role=data.role,
        purpose="team",
        all_brands=data.all_brands or data.role == "owner",
        pre_verified=False,
        sender_profile="transactional",
        send_status="pending",
        reply_token=secrets.token_urlsafe(24),
        invited_by_id=current_user.id,
        expires_at=_now() + timedelta(days=data.expires_days),
    )
    db.add(invite)
    await db.flush()
    await db.commit()
    await db.refresh(invite)
    if data.send_email:
        await _deliver_invite(db, invite)
        await db.commit()
        await db.refresh(invite)
    return _invite_response(invite)


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_team_invite(
    brand_id: int,
    invite_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _, organization, _ = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    invite = await db.scalar(
        select(BrandInvite)
        .where(
            BrandInvite.id == invite_id,
            BrandInvite.organization_id == organization.id,
            BrandInvite.purpose == "team",
        )
        .with_for_update()
    )
    if invite is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_BRAND_INVITE_NOT_FOUND)
    if invite.accepted_at is None and invite.revoked_at is None:
        invite.revoked_at = _now()
    await db.commit()


@router.patch("/members/{membership_id}", status_code=204)
async def update_team_member(
    brand_id: int,
    membership_id: int,
    data: TeamMembershipUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _, organization, _ = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.active.is_(True),
        )
        .with_for_update()
    )
    if membership is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_MEMBERSHIP_NOT_FOUND)
    next_role = OrganizationMemberRole(data.role)
    if (
        membership.role == OrganizationMemberRole.OWNER
        and next_role != OrganizationMemberRole.OWNER
        and await _other_owner_count(
            db, organization_id=organization.id, membership_id=membership.id
        )
        == 0
    ):
        raise_error(status.HTTP_409_CONFLICT, ERR_LAST_ORGANIZATION_OWNER)
    await _replace_scope(
        db,
        organization_id=organization.id,
        membership=membership,
        role=next_role,
        all_brands=data.all_brands,
        brand_ids=data.brand_ids,
    )
    await db.commit()


@router.delete("/members/{membership_id}", status_code=204)
async def remove_team_member(
    brand_id: int,
    membership_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _, organization, _ = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.active.is_(True),
        )
        .with_for_update()
    )
    if membership is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_MEMBERSHIP_NOT_FOUND)
    if (
        membership.role == OrganizationMemberRole.OWNER
        and await _other_owner_count(
            db, organization_id=organization.id, membership_id=membership.id
        )
        == 0
    ):
        raise_error(status.HTTP_409_CONFLICT, ERR_LAST_ORGANIZATION_OWNER)
    member = await db.get(User, membership.user_id)
    membership.active = False
    if member is not None and member.brand_id in {
        row[0]
        for row in (
            await db.execute(select(Brand.id).where(Brand.organization_id == organization.id))
        ).all()
    }:
        member.brand_id = None
    if member is not None:
        remaining = await db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.user_id == member.id,
                OrganizationMembership.active.is_(True),
                OrganizationMembership.id != membership.id,
            )
        )
        if remaining is None and member.role == UserRole.BRAND:
            member.role = UserRole.USER
    await db.commit()


@router.post("/transfer", status_code=204)
async def transfer_ownership(
    brand_id: int,
    data: OwnershipTransferRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    _, organization, current_membership = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    if current_membership is None:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    current_membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == current_membership.id,
            OrganizationMembership.active.is_(True),
        )
        .with_for_update()
    )
    if current_membership is None:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    target = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.id == data.target_membership_id,
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.active.is_(True),
            OrganizationMembership.id != current_membership.id,
        )
        .with_for_update()
    )
    if target is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ORGANIZATION_MEMBERSHIP_NOT_FOUND)
    target.role = OrganizationMemberRole.OWNER
    target.all_brands = True
    current_membership.role = OrganizationMemberRole.EDITOR
    current_membership.all_brands = True
    await db.execute(
        delete(OrganizationBrandAccess).where(
            OrganizationBrandAccess.membership_id.in_([target.id, current_membership.id])
        )
    )
    await db.commit()


@router.patch("/join-requests/{request_id}", status_code=204)
async def decide_join_request(
    brand_id: int,
    request_id: int,
    data: TeamJoinRequestDecision,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    brand, _, _ = await _owner_workspace(
        db, brand_id=brand_id, user=current_user
    )
    if not brand.verified:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    request = await db.scalar(
        select(BrandRequest)
        .where(
            BrandRequest.id == request_id,
            BrandRequest.request_type == BrandRequestType.JOIN,
            BrandRequest.brand_id == brand.id,
        )
        .with_for_update()
    )
    if request is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_REQUEST_NOT_FOUND)
    if request.status != BrandRequestStatus.PENDING:
        raise_error(status.HTTP_409_CONFLICT, ERR_REQUEST_NOT_PENDING)
    request.processed_by_id = current_user.id
    request.processed_at = _now()
    if data.status == "rejected":
        request.status = BrandRequestStatus.REJECTED
        request.rejection_reason = data.rejection_reason
        await notify_brand_request_rejected(
            user_id=request.user_id,
            brand_name=brand.name,
            reason=data.rejection_reason,
            db=db,
        )
        return

    member = await db.get(User, request.user_id)
    if member is None or not member.active:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_USER_NOT_FOUND)
    await grant_brand_editor_membership(
        db,
        brand=brand,
        user=member,
        granted_by_id=current_user.id,
    )
    request.status = BrandRequestStatus.APPROVED
    request.rejection_reason = None
    await notify_brand_request_approved(
        user_id=member.id,
        brand_name=brand.name,
        brand_id=brand.id,
        db=db,
    )
