"""Ownership and authorization rules for personal and official presets."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filament import Filament
from app.models.preset import Preset
from app.models.user import User, UserRole


async def official_preset_organization_id(
    db: AsyncSession,
    user: User,
    filament: Filament,
) -> int | None:
    """Return the Organization that may publish for this active workspace.

    Administrators may create a platform-managed legacy-compatible official
    row. Everyone else must act through one exact Brand + Organization pair.
    """
    if user.role == UserRole.ADMIN:
        if user.active_organization_id is None:
            return None
        from app.services.organization_access import get_workspace_membership

        membership = await get_workspace_membership(
            db,
            user,
            brand_id=filament.brand_id,
            organization_id=user.active_organization_id,
        )
        return user.active_organization_id if membership is not None else None
    if user.active_organization_id is None:
        return None

    from app.models.brand import Brand
    from app.services.organization_access import get_workspace_membership
    from app.services.territorial_access import can_edit_filament_common

    brand = await db.get(Brand, filament.brand_id)
    if brand is None or not brand.verified:
        return None
    membership = await get_workspace_membership(
        db,
        user,
        brand_id=filament.brand_id,
        organization_id=user.active_organization_id,
    )
    if membership is None:
        return None
    if not await can_edit_filament_common(db, user, filament.brand_id):
        return None
    return user.active_organization_id


async def can_manage_preset(
    db: AsyncSession,
    user: User,
    preset: Preset,
    filament: Filament | None = None,
) -> bool:
    """Check the actual owner boundary, not the identity of the first actor."""
    if user.role == UserRole.ADMIN:
        return True
    if not preset.is_official:
        return preset.user_id == user.id
    if filament is None or user.active_organization_id is None:
        return False

    from app.services.organization_access import get_workspace_membership

    membership = await get_workspace_membership(
        db,
        user,
        brand_id=filament.brand_id,
        organization_id=user.active_organization_id,
    )
    if membership is None:
        return False
    # Ambiguous legacy/platform presets are not silently claimed by whichever
    # territorial representative happens to edit first.
    return preset.organization_id == user.active_organization_id
