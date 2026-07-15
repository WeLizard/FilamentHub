"""Authorization helpers for organization-owned brands.

``User.brand_id`` is only the user's active workspace pointer. Access to a
company workspace always comes from an active organization membership. Global
administrators use dedicated moderation endpoints instead of entering company
workspaces implicitly.
"""

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.organization import (
    Organization,
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole
from app.services.slug_service import generate_unique_slug

BRAND_EDITOR_ROLES = {
    OrganizationMemberRole.OWNER,
    OrganizationMemberRole.EDITOR,
}


async def grant_brand_owner_membership(
    db: AsyncSession,
    *,
    brand: Brand,
    user: User,
    granted_by_id: int | None = None,
) -> tuple[Organization, OrganizationMembership]:
    """Grant a verified representative owner access to a public brand.

    The public Brand remains the catalog identity. An Organization is created
    only when the brand has no owner workspace yet; existing organizations and
    accumulated community content are preserved.
    """
    organization = (
        await db.get(Organization, brand.organization_id)
        if brand.organization_id is not None
        else None
    )
    if organization is None:
        organization = Organization(
            name=brand.name,
            slug=await generate_unique_slug(
                db=db,
                model=Organization,
                source=brand.name,
                fallback="organization",
            ),
            created_by_id=user.id,
            active=True,
        )
        db.add(organization)
        await db.flush()
        brand.organization_id = organization.id
    else:
        await db.execute(
            select(Organization.id)
            .where(Organization.id == organization.id)
            .with_for_update()
        )

    membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
        .with_for_update()
    )
    if membership is None:
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            all_brands=True,
            active=True,
            invited_by_id=granted_by_id,
        )
        db.add(membership)
    else:
        membership.role = OrganizationMemberRole.OWNER
        membership.all_brands = True
        membership.active = True
        if membership.invited_by_id is None:
            membership.invited_by_id = granted_by_id

    user.brand_id = brand.id
    if user.role == UserRole.USER:
        user.role = UserRole.BRAND

    await db.flush()
    return organization, membership


async def grant_brand_editor_membership(
    db: AsyncSession,
    *,
    brand: Brand,
    user: User,
    granted_by_id: int | None = None,
) -> tuple[Organization, OrganizationMembership]:
    """Grant editor access to one brand in an already owned organization."""
    if brand.organization_id is None:
        raise ValueError("Brand organization is required for an editor membership")
    organization = await db.get(Organization, brand.organization_id)
    if organization is None or not organization.active:
        raise ValueError("Active brand organization is required for an editor membership")

    await db.execute(
        select(Organization.id)
        .where(Organization.id == organization.id)
        .with_for_update()
    )
    membership = await db.scalar(
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
        .with_for_update()
    )
    if membership is None:
        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMemberRole.EDITOR,
            all_brands=False,
            active=True,
            invited_by_id=granted_by_id,
        )
        db.add(membership)
        await db.flush()
    elif not membership.active:
        membership.role = OrganizationMemberRole.EDITOR
        membership.all_brands = False
        membership.active = True
        membership.invited_by_id = granted_by_id
        await db.execute(
            delete(OrganizationBrandAccess).where(
                OrganizationBrandAccess.membership_id == membership.id
            )
        )

    if membership.role != OrganizationMemberRole.OWNER and not membership.all_brands:
        access = await db.scalar(
            select(OrganizationBrandAccess).where(
                OrganizationBrandAccess.membership_id == membership.id,
                OrganizationBrandAccess.brand_id == brand.id,
            )
        )
        if access is None:
            db.add(OrganizationBrandAccess(membership_id=membership.id, brand_id=brand.id))

    user.brand_id = brand.id
    if user.role == UserRole.USER:
        user.role = UserRole.BRAND
    await db.flush()
    return organization, membership


async def get_brand_membership(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> OrganizationMembership | None:
    """Return the active membership that grants access to ``brand_id``."""
    query = (
        select(OrganizationMembership)
        .join(Brand, Brand.organization_id == OrganizationMembership.organization_id)
        .outerjoin(
            OrganizationBrandAccess,
            OrganizationBrandAccess.membership_id == OrganizationMembership.id,
        )
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
            Brand.id == brand_id,
            or_(
                OrganizationMembership.all_brands.is_(True),
                OrganizationBrandAccess.brand_id == brand_id,
            ),
        )
        .limit(1)
    )
    return await db.scalar(query)


async def list_accessible_brands(
    db: AsyncSession,
    user: User,
) -> list[tuple[Brand, Organization, OrganizationMembership]]:
    """List brands the user may select as their active brand.

    Every user, including a global administrator, only sees brands granted by
    an active organization membership and its optional per-brand scope.
    """
    result = await db.execute(
        select(Brand, Organization, OrganizationMembership)
        .join(Organization, Brand.organization_id == Organization.id)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .outerjoin(
            OrganizationBrandAccess,
            OrganizationBrandAccess.membership_id == OrganizationMembership.id,
        )
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
            Organization.active.is_(True),
            Brand.active.is_(True),
            or_(
                OrganizationMembership.all_brands.is_(True),
                OrganizationBrandAccess.brand_id == Brand.id,
            ),
        )
        .distinct()
        .order_by(Organization.name.asc(), Brand.name.asc())
    )
    return list(result.all())


async def can_select_active_brand(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> bool:
    """Whether ``brand_id`` is a valid workspace choice for ``user``."""
    return await get_brand_membership(db, user, brand_id) is not None


async def revoke_brand_membership(
    db: AsyncSession,
    *,
    user: User,
    brand_id: int,
) -> bool:
    """Revoke the organization membership that grants access to a brand."""
    membership = await get_brand_membership(db, user, brand_id)
    if membership is None:
        return False

    membership.active = False
    if user.brand_id == brand_id:
        user.brand_id = None

    remaining = await db.scalar(
        select(OrganizationMembership.id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.active.is_(True),
            OrganizationMembership.id != membership.id,
        )
        .limit(1)
    )
    if remaining is None and user.role == UserRole.BRAND:
        user.role = UserRole.USER

    await db.flush()
    return True


async def can_view_private_brand_data(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> bool:
    """Whether a user may view private manufacturer analytics/settings."""
    if user.role == UserRole.ADMIN:
        return True
    return await get_brand_membership(db, user, brand_id) is not None


async def can_edit_brand_catalog(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> bool:
    """Whether a user may edit official brand and filament catalog data."""
    if user.role == UserRole.ADMIN:
        return True
    membership = await get_brand_membership(db, user, brand_id)
    return membership is not None and membership.role in BRAND_EDITOR_ROLES
