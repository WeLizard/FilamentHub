"""Idempotent achievement evaluation based on durable useful actions."""

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user_achievement import UserAchievement
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.achievement import AchievementOverviewResponse, AchievementResponse

FIRST_CATALOG_CONTRIBUTION = "first_catalog_contribution"
FIRST_PROFILE = "first_profile"
PRESET_USED_BY_ANOTHER = "preset_used_by_another"


async def award_achievement(
    db: AsyncSession,
    *,
    user_id: int,
    code: str,
    evidence_type: str | None = None,
    evidence_id: int | None = None,
) -> UserAchievement:
    """Return the existing award or stage the user's first matching award."""
    existing = await db.scalar(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code == code,
        )
    )
    if existing is not None:
        return existing
    achievement = UserAchievement(
        user_id=user_id,
        code=code,
        evidence_type=evidence_type,
        evidence_id=evidence_id,
    )
    try:
        async with db.begin_nested():
            db.add(achievement)
            await db.flush()
    except IntegrityError:
        concurrent = await db.scalar(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.code == code,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    return achievement


async def _published_preset_count(db: AsyncSession, user_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count(Preset.id)).where(
                Preset.user_id == user_id,
                Preset.active.is_(True),
                Preset.filament_id.is_not(None),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_weighted.is_(False),
            )
        )
        or 0
    )


async def _other_user_save_count(db: AsyncSession, user_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count(distinct(UserSavedPreset.user_id)))
            .join(Preset, Preset.id == UserSavedPreset.preset_id)
            .where(
                Preset.user_id == user_id,
                UserSavedPreset.user_id != user_id,
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
        )
        or 0
    )


async def _other_user_confirmed_use_count(db: AsyncSession, user_id: int) -> int:
    return int(
        await db.scalar(
            select(func.count(distinct(PresetUsageEvent.user_id)))
            .join(Preset, Preset.id == PresetUsageEvent.preset_id)
            .where(
                Preset.user_id == user_id,
                PresetUsageEvent.user_id != user_id,
                PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
        )
        or 0
    )


async def achievement_overview(
    db: AsyncSession,
    *,
    user_id: int,
) -> AchievementOverviewResponse:
    """Evaluate retroactive milestones and return only factual contribution data."""
    published_presets = await _published_preset_count(db, user_id)
    saved_by_others = await _other_user_save_count(db, user_id)
    confirmed_uses = await _other_user_confirmed_use_count(db, user_id)

    if published_presets:
        first_preset_id = await db.scalar(
            select(Preset.id)
            .where(
                Preset.user_id == user_id,
                Preset.active.is_(True),
                Preset.filament_id.is_not(None),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
                Preset.is_weighted.is_(False),
            )
            .order_by(Preset.created_at.asc(), Preset.id.asc())
            .limit(1)
        )
        await award_achievement(
            db,
            user_id=user_id,
            code=FIRST_PROFILE,
            evidence_type="preset",
            evidence_id=first_preset_id,
        )
    # Saving with sync enabled is only desired state. The historical award says
    # another person actually imported/used the profile, so wait for durable
    # printer evidence instead of turning a bookmark into reputation.
    if confirmed_uses:
        await award_achievement(
            db,
            user_id=user_id,
            code=PRESET_USED_BY_ANOTHER,
            evidence_type="preset_usage",
        )

    await db.commit()
    rows = list(
        await db.scalars(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .order_by(UserAchievement.earned_at.asc(), UserAchievement.id.asc())
        )
    )
    return AchievementOverviewResponse(
        achievements=[
            AchievementResponse(code=row.code, earned_at=row.earned_at) for row in rows
        ],
        published_presets=published_presets,
        saved_by_other_users=saved_by_others,
        confirmed_uses_by_other_users=confirmed_uses,
    )
