"""Achievement registry, retroactive evaluation, and factual contributor summary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_system import MaterialSystem
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.schemas.achievement import (
    AchievementOverviewResponse,
    AchievementProgressResponse,
    AchievementResponse,
)

FIRST_CATALOG_CONTRIBUTION = "first_catalog_contribution"
FIRST_PROFILE = "first_profile"
PRESET_PUBLISHER_5 = "preset_publisher_5"
PRESET_USED_BY_ANOTHER = "preset_used_by_another"
PRESETS_USED_BY_10 = "presets_used_by_10"
SPOOL_COLLECTOR_20 = "spool_collector_20"
SPOOL_COLLECTOR_100 = "spool_collector_100"
HAPPY_HARE_CONNECTED = "happy_hare_connected"
FIRST_WIKI_ARTICLE = "first_wiki_article"
FIRST_HUNDRED = "first_hundred"

AchievementMetric = Literal[
    "published_presets",
    "confirmed_users",
    "spools",
    "happy_hare",
    "wiki_articles",
    "first_hundred",
]


@dataclass(frozen=True, slots=True)
class AchievementDefinition:
    code: str
    category: str
    rarity: str
    family: str
    metric: AchievementMetric | None
    target: int
    sort_order: int
    hidden: bool = False
    show_progress: bool = True
    auto_evaluate: bool = True


@dataclass(frozen=True, slots=True)
class AchievementMetrics:
    published_presets: int
    saved_by_other_users: int
    confirmed_users: int
    spools: int
    happy_hare: int
    wiki_articles: int
    first_hundred: int


# Definitions are code-backed. Award rows keep immutable history while new
# presentation and thresholds do not duplicate reference data for every user.
ACHIEVEMENT_DEFINITIONS = (
    AchievementDefinition(
        code=FIRST_HUNDRED,
        category="history",
        rarity="historic",
        family="registration_history",
        metric="first_hundred",
        target=1,
        sort_order=10,
        show_progress=False,
    ),
    AchievementDefinition(
        code=FIRST_CATALOG_CONTRIBUTION,
        category="catalog",
        rarity="common",
        family="catalog_contribution",
        metric=None,
        target=1,
        sort_order=20,
        auto_evaluate=False,
    ),
    AchievementDefinition(
        code=FIRST_PROFILE,
        category="presets",
        rarity="common",
        family="preset_publication",
        metric="published_presets",
        target=1,
        sort_order=30,
    ),
    AchievementDefinition(
        code=PRESET_PUBLISHER_5,
        category="presets",
        rarity="uncommon",
        family="preset_publication",
        metric="published_presets",
        target=5,
        sort_order=40,
    ),
    AchievementDefinition(
        code=PRESET_USED_BY_ANOTHER,
        category="presets",
        rarity="uncommon",
        family="preset_usefulness",
        metric="confirmed_users",
        target=1,
        sort_order=50,
    ),
    AchievementDefinition(
        code=PRESETS_USED_BY_10,
        category="presets",
        rarity="rare",
        family="preset_usefulness",
        metric="confirmed_users",
        target=10,
        sort_order=60,
    ),
    AchievementDefinition(
        code=SPOOL_COLLECTOR_20,
        category="inventory",
        rarity="uncommon",
        family="spool_collection",
        metric="spools",
        target=20,
        sort_order=70,
    ),
    AchievementDefinition(
        code=SPOOL_COLLECTOR_100,
        category="inventory",
        rarity="secret",
        family="spool_collection",
        metric="spools",
        target=100,
        sort_order=80,
        hidden=True,
        show_progress=False,
    ),
    AchievementDefinition(
        code=HAPPY_HARE_CONNECTED,
        category="integrations",
        rarity="uncommon",
        family="happy_hare",
        metric="happy_hare",
        target=1,
        sort_order=90,
    ),
    AchievementDefinition(
        code=FIRST_WIKI_ARTICLE,
        category="wiki",
        rarity="common",
        family="wiki_publication",
        metric="wiki_articles",
        target=1,
        sort_order=100,
    ),
)

_DEFINITIONS_BY_CODE = {item.code: item for item in ACHIEVEMENT_DEFINITIONS}


async def award_achievement(
    db: AsyncSession,
    *,
    user_id: int,
    code: str,
    evidence_type: str | None = None,
    evidence_id: int | None = None,
    earned_at: datetime | None = None,
) -> UserAchievement:
    """Return the existing award or stage the user's first matching award."""
    if code not in _DEFINITIONS_BY_CODE:
        raise ValueError(f"Unknown achievement code: {code}")
    existing = await db.scalar(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.code == code,
        )
    )
    if existing is not None:
        return existing
    values: dict[str, object] = {
        "user_id": user_id,
        "code": code,
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
    }
    if earned_at is not None:
        values["earned_at"] = earned_at
    achievement = UserAchievement(**values)
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


def _published_preset_filter(user_id: int) -> tuple[object, ...]:
    return (
        Preset.user_id == user_id,
        Preset.active.is_(True),
        Preset.filament_id.is_not(None),
        Preset.moderation_status == PresetModerationStatus.APPROVED,
        Preset.is_weighted.is_(False),
    )


async def _achievement_metrics(db: AsyncSession, user_id: int) -> AchievementMetrics:
    published_presets = int(
        await db.scalar(select(func.count(Preset.id)).where(*_published_preset_filter(user_id)))
        or 0
    )
    saved_by_others = int(
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
    confirmed_users = int(
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
    spools = int(
        await db.scalar(select(func.count(UserSpool.id)).where(UserSpool.user_id == user_id)) or 0
    )
    happy_hare = int(
        await db.scalar(
            select(func.count(MaterialSystem.id)).where(
                MaterialSystem.user_id == user_id,
                MaterialSystem.active.is_(True),
                MaterialSystem.provider == "happy_hare",
            )
        )
        or 0
    )
    wiki_articles = int(
        await db.scalar(
            select(func.count(WikiArticle.id)).where(
                WikiArticle.created_by_id == user_id,
                WikiArticle.status == WikiArticleStatus.PUBLISHED,
                WikiArticle.published.is_(True),
            )
        )
        or 0
    )
    user = await db.scalar(select(User).where(User.id == user_id))
    first_hundred = int(user is not None and user.id <= 100)
    return AchievementMetrics(
        published_presets=published_presets,
        saved_by_other_users=saved_by_others,
        confirmed_users=confirmed_users,
        spools=spools,
        happy_hare=happy_hare,
        wiki_articles=wiki_articles,
        first_hundred=first_hundred,
    )


def _metric_value(definition: AchievementDefinition, metrics: AchievementMetrics) -> int:
    if definition.metric is None:
        return 0
    return int(getattr(metrics, definition.metric))


async def _threshold_evidence(
    db: AsyncSession,
    *,
    user_id: int,
    definition: AchievementDefinition,
) -> tuple[str | None, int | None, datetime | None]:
    """Return the durable row and best reconstructable time for a threshold."""
    if definition.metric == "published_presets":
        publication_time = func.coalesce(Preset.moderated_at, Preset.updated_at, Preset.created_at)
        row = (
            await db.execute(
                select(Preset.id, publication_time)
                .where(*_published_preset_filter(user_id))
                .order_by(publication_time.asc(), Preset.id.asc())
                .offset(definition.target - 1)
                .limit(1)
            )
        ).first()
        return ("preset", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "confirmed_users":
        first_uses = (
            select(
                PresetUsageEvent.user_id.label("reader_id"),
                func.min(PresetUsageEvent.created_at).label("first_used_at"),
            )
            .join(Preset, Preset.id == PresetUsageEvent.preset_id)
            .where(
                Preset.user_id == user_id,
                PresetUsageEvent.user_id != user_id,
                PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                Preset.active.is_(True),
                Preset.moderation_status == PresetModerationStatus.APPROVED,
            )
            .group_by(PresetUsageEvent.user_id)
            .subquery()
        )
        row = (
            await db.execute(
                select(first_uses.c.reader_id, first_uses.c.first_used_at)
                .order_by(first_uses.c.first_used_at.asc(), first_uses.c.reader_id.asc())
                .offset(definition.target - 1)
                .limit(1)
            )
        ).first()
        return ("preset_usage", None, row[1]) if row else (None, None, None)
    if definition.metric == "spools":
        row = (
            await db.execute(
                select(UserSpool.id, UserSpool.created_at)
                .where(UserSpool.user_id == user_id)
                .order_by(UserSpool.created_at.asc(), UserSpool.id.asc())
                .offset(definition.target - 1)
                .limit(1)
            )
        ).first()
        return ("user_spool", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "happy_hare":
        row = (
            await db.execute(
                select(MaterialSystem.id, MaterialSystem.created_at)
                .where(
                    MaterialSystem.user_id == user_id,
                    MaterialSystem.active.is_(True),
                    MaterialSystem.provider == "happy_hare",
                )
                .order_by(MaterialSystem.created_at.asc(), MaterialSystem.id.asc())
                .limit(1)
            )
        ).first()
        return ("material_system", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "wiki_articles":
        row = (
            await db.execute(
                select(WikiArticle.id, WikiArticle.updated_at)
                .where(
                    WikiArticle.created_by_id == user_id,
                    WikiArticle.status == WikiArticleStatus.PUBLISHED,
                    WikiArticle.published.is_(True),
                )
                .order_by(WikiArticle.updated_at.asc(), WikiArticle.id.asc())
                .limit(1)
            )
        ).first()
        return ("wiki_article", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "first_hundred":
        user = await db.scalar(select(User).where(User.id == user_id))
        if user is not None and user.id <= 100:
            return "user_registration", user.id, user.created_at
    return None, None, None


def _achievement_response(row: UserAchievement) -> AchievementResponse:
    definition = _DEFINITIONS_BY_CODE.get(row.code)
    return AchievementResponse(
        code=row.code,
        earned_at=row.earned_at,
        category=definition.category if definition else "legacy",
        rarity=definition.rarity if definition else "common",
        hidden=definition.hidden if definition else False,
    )


def _contributor_roles(earned_codes: set[str]) -> list[str]:
    roles: list[str] = []
    if FIRST_CATALOG_CONTRIBUTION in earned_codes:
        roles.append("catalog_contributor")
    if FIRST_PROFILE in earned_codes:
        roles.append("preset_author")
    if HAPPY_HARE_CONNECTED in earned_codes:
        roles.append("hardware_integrator")
    if FIRST_WIKI_ARTICLE in earned_codes:
        roles.append("wiki_contributor")
    if SPOOL_COLLECTOR_20 in earned_codes:
        roles.append("collector")
    return roles


def _next_achievement_progress(
    *, earned_codes: set[str], metrics: AchievementMetrics
) -> list[AchievementProgressResponse]:
    next_by_family: dict[str, AchievementProgressResponse] = {}
    for definition in ACHIEVEMENT_DEFINITIONS:
        if definition.code in earned_codes or definition.hidden or not definition.show_progress:
            continue
        current = 0 if definition.metric is None else _metric_value(definition, metrics)
        if definition.family in next_by_family:
            continue
        next_by_family[definition.family] = AchievementProgressResponse(
            code=definition.code,
            category=definition.category,
            rarity=definition.rarity,
            current=min(current, definition.target),
            target=definition.target,
        )
    return list(next_by_family.values())


async def _build_overview(
    db: AsyncSession,
    *,
    user_id: int,
    metrics: AchievementMetrics | None = None,
    newly_earned: list[str] | None = None,
) -> AchievementOverviewResponse:
    metrics = metrics or await _achievement_metrics(db, user_id)
    rows = list(
        await db.scalars(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .order_by(UserAchievement.earned_at.desc(), UserAchievement.id.desc())
        )
    )
    earned_codes = {row.code for row in rows}
    return AchievementOverviewResponse(
        achievements=[_achievement_response(row) for row in rows],
        next_achievements=_next_achievement_progress(earned_codes=earned_codes, metrics=metrics),
        newly_earned=newly_earned or [],
        contributor_roles=_contributor_roles(earned_codes),
        published_presets=metrics.published_presets,
        saved_by_other_users=metrics.saved_by_other_users,
        confirmed_uses_by_other_users=metrics.confirmed_users,
    )


async def read_achievement_overview(
    db: AsyncSession, *, user_id: int
) -> AchievementOverviewResponse:
    """Return current immutable awards and live factual progress without writes."""
    return await _build_overview(db, user_id=user_id)


async def evaluate_achievement_overview(
    db: AsyncSession, *, user_id: int
) -> AchievementOverviewResponse:
    """Retroactively award every threshold supported by durable current facts."""
    metrics = await _achievement_metrics(db, user_id)
    existing_codes = set(
        await db.scalars(select(UserAchievement.code).where(UserAchievement.user_id == user_id))
    )
    newly_earned: list[str] = []
    for definition in ACHIEVEMENT_DEFINITIONS:
        if (
            not definition.auto_evaluate
            or definition.code in existing_codes
            or _metric_value(definition, metrics) < definition.target
        ):
            continue
        evidence_type, evidence_id, occurred_at = await _threshold_evidence(
            db, user_id=user_id, definition=definition
        )
        await award_achievement(
            db,
            user_id=user_id,
            code=definition.code,
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            earned_at=occurred_at,
        )
        newly_earned.append(definition.code)
        existing_codes.add(definition.code)
    await db.commit()
    return await _build_overview(
        db,
        user_id=user_id,
        metrics=metrics,
        newly_earned=newly_earned,
    )


# Compatibility for internal callers introduced by the first motivation slice.
achievement_overview = evaluate_achievement_overview
