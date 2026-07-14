"""Authorization helpers for organization-owned brands.

The legacy ``User.brand_id`` relationship remains a compatibility fallback
while existing accounts and UI are migrated to scoped organization memberships.
"""

from sqlalchemy import or_, select
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


async def can_view_private_brand_data(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> bool:
    """Whether a user may view private manufacturer analytics/settings."""
    if user.role == UserRole.ADMIN or user.brand_id == brand_id:
        return True
    return await get_brand_membership(db, user, brand_id) is not None


async def can_edit_brand_catalog(
    db: AsyncSession,
    user: User,
    brand_id: int,
) -> bool:
    """Whether a user may edit official brand and filament catalog data."""
    if user.role == UserRole.ADMIN or user.brand_id == brand_id:
        return True
    membership = await get_brand_membership(db, user, brand_id)
    return membership is not None and membership.role in BRAND_EDITOR_ROLES
