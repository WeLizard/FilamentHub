"""Visibility checks for stable slicer identities supplied by user-owned files."""

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset import PUBLIC_PRESET_STATUSES, Preset
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile


async def visible_material_presets(
    db: AsyncSession, *, user_id: int, preset_ids: set[int]
) -> dict[int, Preset]:
    if not preset_ids:
        return {}
    result = await db.execute(
        select(Preset).where(
            Preset.id.in_(preset_ids),
            or_(
                Preset.user_id == user_id,
                and_(
                    Preset.active.is_(True),
                    Preset.moderation_status.in_(PUBLIC_PRESET_STATUSES),
                ),
            ),
        )
    )
    return {preset.id: preset for preset in result.scalars().all()}


async def visible_print_profile_ids(
    db: AsyncSession, *, user_id: int, profile_ids: set[int]
) -> set[int]:
    if not profile_ids:
        return set()
    result = await db.execute(
        select(PrintProfile.id).where(
            PrintProfile.id.in_(profile_ids),
            or_(
                PrintProfile.owner_user_id == user_id,
                and_(
                    PrintProfile.active.is_(True),
                    PrintProfile.is_official.is_(True),
                ),
            ),
        )
    )
    return set(result.scalars().all())


async def visible_printer_profile_ids(
    db: AsyncSession, *, user_id: int, profile_ids: set[int]
) -> set[int]:
    if not profile_ids:
        return set()
    linked_ids = set(
        (
            await db.execute(
                select(UserPrinterProfileLink.printer_profile_id).where(
                    UserPrinterProfileLink.user_id == user_id,
                    UserPrinterProfileLink.printer_profile_id.in_(profile_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    result = await db.execute(
        select(PrinterProfile.id).where(
            PrinterProfile.id.in_(profile_ids),
            or_(
                PrinterProfile.owner_user_id == user_id,
                PrinterProfile.id.in_(linked_ids),
                and_(
                    PrinterProfile.active.is_(True),
                    PrinterProfile.is_official.is_(True),
                ),
            ),
        )
    )
    return set(result.scalars().all())
