"""Authorization helpers for organization-owned brands.

The legacy ``User.brand_id`` relationship remains a compatibility fallback
while existing accounts and UI are migrated to scoped organization memberships.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.organization import (
    OrganizationBrandAccess,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.user import User, UserRole

BRAND_EDITOR_ROLES = {
    OrganizationMemberRole.OWNER,
    OrganizationMemberRole.EDITOR,
}


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
