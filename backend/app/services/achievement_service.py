"""Achievement registry, factual evaluation, and audited manual distinctions."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_ACHIEVEMENT_ALREADY_AWARDED,
    ERR_ACHIEVEMENT_NOT_AWARDED,
    ERR_ACHIEVEMENT_NOT_MANUAL,
    ERR_ACHIEVEMENT_REGRANT_FORBIDDEN,
)
from app.models.filament import Filament
from app.models.material_slot_assignment import MaterialSlotAssignment
from app.models.material_system import MaterialSlot, MaterialSystem, PhysicalPrinterConnector
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_usage_event import PresetUsageEvent, PresetUsageEventType
from app.models.user import User
from app.models.user_achievement import UserAchievement
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle, WikiArticleStatus
from app.models.wiki_revision import (
    WikiRevision,
    WikiRevisionAuthorship,
    WikiRevisionStatus,
)
from app.schemas.achievement import (
    AchievementOverviewResponse,
    AchievementProgressResponse,
    AchievementResponse,
    AdminAchievementOverviewResponse,
    AdminAchievementResponse,
)

FIRST_HUNDRED = "first_hundred"
PROJECT_FOUNDER = "project_founder"
BETA_TESTER = "beta_tester"
PROJECT_CONTRIBUTOR = "project_contributor"
PROJECT_SUPPORTER = "project_supporter"
EARLY_ADOPTER = "early_adopter"
FIRST_CATALOG_CONTRIBUTION = "first_catalog_contribution"
FIRST_PROFILE = "first_profile"
PRESET_PUBLISHER_5 = "preset_publisher_5"
PRESET_PUBLISHER_20 = "preset_publisher_20"
PRESET_PUBLISHER_50 = "preset_publisher_50"
PRESET_USED_BY_ANOTHER = "preset_used_by_another"
PRESETS_USED_BY_3 = "presets_used_by_3"
PRESETS_USED_BY_10 = "presets_used_by_10"
PRESET_CONFIRMED_BY_AUTHOR = "preset_confirmed_by_author"
PRESET_MATERIAL_TYPES_5 = "preset_material_types_5"
SPOOL_COLLECTOR_1 = "spool_collector_1"
SPOOL_COLLECTOR_20 = "spool_collector_20"
SPOOL_COLLECTOR_100 = "spool_collector_100"
MATERIAL_SYSTEM_CONNECTED = "material_system_connected"
HAPPY_HARE_CONNECTED = "happy_hare_connected"
PRINTER_INTEGRATION_CONNECTED = "printer_integration_connected"
AUTOMATIC_SPOOL_ASSIGNMENT = "automatic_spool_assignment"
FULL_MATERIAL_SYSTEM = "full_material_system"
SPOOL_DEPLETED_BY_PRINT = "spool_depleted_by_print"
FIRST_WIKI_ARTICLE = "first_wiki_article"
FIRST_WIKI_REVISION = "first_wiki_revision"
WIKI_EDITOR_5 = "wiki_editor_5"

AchievementMetric = Literal[
    "published_presets",
    "confirmed_users",
    "confirmed_own_prints",
    "preset_material_types",
    "spools",
    "material_systems",
    "happy_hare",
    "connectors",
    "automatic_assignments",
    "full_material_systems",
    "depleted_spools",
    "wiki_articles",
    "wiki_revisions",
    "first_hundred",
]
AchievementAwardMode = Literal["automatic", "manual", "migration"]


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
    award_mode: AchievementAwardMode = "automatic"


@dataclass(frozen=True, slots=True)
class AchievementMetrics:
    published_presets: int
    saved_by_other_users: int
    confirmed_users: int
    confirmed_own_prints: int
    preset_material_types: int
    spools: int
    material_systems: int
    happy_hare: int
    connectors: int
    automatic_assignments: int
    full_material_systems: int
    depleted_spools: int
    wiki_articles: int
    wiki_revisions: int
    first_hundred: int


def _manual_definition(
    code: str,
    sort_order: int,
    *,
    category: str = "community",
    rarity: str = "honor",
) -> AchievementDefinition:
    return AchievementDefinition(
        code=code,
        category=category,
        rarity=rarity,
        family=f"manual:{code}",
        metric=None,
        target=1,
        sort_order=sort_order,
        show_progress=False,
        auto_evaluate=False,
        award_mode="manual",
    )


ACHIEVEMENT_DEFINITIONS = (
    AchievementDefinition(
        FIRST_HUNDRED,
        "history",
        "historic",
        "registration_history",
        "first_hundred",
        1,
        10,
        show_progress=False,
    ),
    _manual_definition(PROJECT_FOUNDER, 11, category="history", rarity="historic"),
    _manual_definition(BETA_TESTER, 12),
    _manual_definition(PROJECT_CONTRIBUTOR, 13),
    _manual_definition(PROJECT_SUPPORTER, 14),
    _manual_definition(EARLY_ADOPTER, 15, category="history", rarity="historic"),
    AchievementDefinition(
        FIRST_CATALOG_CONTRIBUTION,
        "catalog",
        "common",
        "catalog_contribution",
        None,
        1,
        20,
        auto_evaluate=False,
    ),
    AchievementDefinition(
        FIRST_PROFILE, "presets", "common", "preset_publication", "published_presets", 1, 30
    ),
    AchievementDefinition(
        PRESET_PUBLISHER_5, "presets", "uncommon", "preset_publication", "published_presets", 5, 40
    ),
    AchievementDefinition(
        PRESET_PUBLISHER_20, "presets", "rare", "preset_publication", "published_presets", 20, 41
    ),
    AchievementDefinition(
        PRESET_PUBLISHER_50, "presets", "epic", "preset_publication", "published_presets", 50, 42
    ),
    AchievementDefinition(
        PRESET_USED_BY_ANOTHER, "presets", "uncommon", "preset_usefulness", "confirmed_users", 1, 50
    ),
    AchievementDefinition(
        PRESETS_USED_BY_3, "presets", "uncommon", "preset_usefulness", "confirmed_users", 3, 51
    ),
    AchievementDefinition(
        PRESETS_USED_BY_10, "presets", "rare", "preset_usefulness", "confirmed_users", 10, 52
    ),
    AchievementDefinition(
        PRESET_CONFIRMED_BY_AUTHOR,
        "presets",
        "common",
        "preset_validation",
        "confirmed_own_prints",
        1,
        55,
    ),
    AchievementDefinition(
        PRESET_MATERIAL_TYPES_5,
        "presets",
        "rare",
        "material_knowledge",
        "preset_material_types",
        5,
        56,
    ),
    AchievementDefinition(
        SPOOL_COLLECTOR_1, "inventory", "common", "spool_collection", "spools", 1, 60
    ),
    AchievementDefinition(
        SPOOL_COLLECTOR_20, "inventory", "uncommon", "spool_collection", "spools", 20, 61
    ),
    AchievementDefinition(
        SPOOL_COLLECTOR_100,
        "inventory",
        "secret",
        "spool_collection",
        "spools",
        100,
        62,
        hidden=True,
        show_progress=False,
    ),
    AchievementDefinition(
        MATERIAL_SYSTEM_CONNECTED,
        "integrations",
        "common",
        "material_system",
        "material_systems",
        1,
        70,
    ),
    AchievementDefinition(
        HAPPY_HARE_CONNECTED,
        "integrations",
        "secret",
        "happy_hare",
        "happy_hare",
        1,
        71,
        hidden=True,
        show_progress=False,
    ),
    AchievementDefinition(
        PRINTER_INTEGRATION_CONNECTED,
        "integrations",
        "uncommon",
        "printer_integration",
        "connectors",
        1,
        72,
    ),
    AchievementDefinition(
        AUTOMATIC_SPOOL_ASSIGNMENT,
        "integrations",
        "uncommon",
        "automatic_assignment",
        "automatic_assignments",
        1,
        73,
    ),
    AchievementDefinition(
        FULL_MATERIAL_SYSTEM,
        "integrations",
        "secret",
        "full_material_system",
        "full_material_systems",
        1,
        74,
        hidden=True,
        show_progress=False,
    ),
    AchievementDefinition(
        SPOOL_DEPLETED_BY_PRINT,
        "inventory",
        "secret",
        "spool_depletion",
        "depleted_spools",
        1,
        75,
        hidden=True,
        show_progress=False,
    ),
    AchievementDefinition(
        FIRST_WIKI_ARTICLE, "wiki", "common", "wiki_publication", "wiki_articles", 1, 80
    ),
    AchievementDefinition(
        FIRST_WIKI_REVISION, "wiki", "common", "wiki_revision", "wiki_revisions", 1, 81
    ),
    AchievementDefinition(
        WIKI_EDITOR_5, "wiki", "uncommon", "wiki_revision", "wiki_revisions", 5, 82
    ),
)

_DEFINITIONS_BY_CODE = {item.code: item for item in ACHIEVEMENT_DEFINITIONS}
MANUAL_ACHIEVEMENT_CODES = tuple(
    item.code for item in ACHIEVEMENT_DEFINITIONS if item.award_mode == "manual"
)


class ManualAchievementError(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


async def award_achievement(
    db: AsyncSession,
    *,
    user_id: int,
    code: str,
    evidence_type: str | None = None,
    evidence_id: int | None = None,
    earned_at: datetime | None = None,
) -> UserAchievement:
    """Return the existing award or stage the user's first automatic award."""
    definition = _DEFINITIONS_BY_CODE.get(code)
    if definition is None:
        raise ValueError(f"Unknown achievement code: {code}")
    if definition.award_mode != "automatic":
        raise ValueError(f"Achievement is not automatic: {code}")
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
        "source": "automatic",
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
    published_presets = (
        select(func.count(Preset.id)).where(*_published_preset_filter(user_id)).scalar_subquery()
    )
    saved_by_others = (
        select(func.count(distinct(UserSavedPreset.user_id)))
        .join(Preset, Preset.id == UserSavedPreset.preset_id)
        .where(
            Preset.user_id == user_id,
            UserSavedPreset.user_id != user_id,
            Preset.active.is_(True),
            Preset.moderation_status == PresetModerationStatus.APPROVED,
        )
        .scalar_subquery()
    )
    confirmed_users = (
        select(func.count(distinct(PresetUsageEvent.user_id)))
        .join(Preset, Preset.id == PresetUsageEvent.preset_id)
        .where(
            Preset.user_id == user_id,
            PresetUsageEvent.user_id != user_id,
            PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
            Preset.active.is_(True),
            Preset.moderation_status == PresetModerationStatus.APPROVED,
        )
        .scalar_subquery()
    )
    confirmed_own_prints = (
        select(func.count(PresetUsageEvent.id))
        .join(Preset, Preset.id == PresetUsageEvent.preset_id)
        .where(
            Preset.user_id == user_id,
            PresetUsageEvent.user_id == user_id,
            PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
            Preset.active.is_(True),
            Preset.moderation_status == PresetModerationStatus.APPROVED,
        )
        .scalar_subquery()
    )
    preset_material_types = (
        select(func.count(distinct(Filament.material_type)))
        .select_from(Preset)
        .join(Filament, Filament.id == Preset.filament_id)
        .where(*_published_preset_filter(user_id))
        .scalar_subquery()
    )
    spools = select(func.count(UserSpool.id)).where(UserSpool.user_id == user_id).scalar_subquery()
    active_slot_count = (
        select(func.count(MaterialSlot.id))
        .where(MaterialSlot.material_system_id == MaterialSystem.id, MaterialSlot.active.is_(True))
        .correlate(MaterialSystem)
        .scalar_subquery()
    )
    material_systems = (
        select(func.count(MaterialSystem.id))
        .where(
            MaterialSystem.user_id == user_id,
            MaterialSystem.active.is_(True),
            active_slot_count >= 2,
        )
        .scalar_subquery()
    )
    happy_hare = (
        select(func.count(MaterialSystem.id))
        .where(
            MaterialSystem.user_id == user_id,
            MaterialSystem.active.is_(True),
            MaterialSystem.provider == "happy_hare",
        )
        .scalar_subquery()
    )
    connectors = (
        select(func.count(PhysicalPrinterConnector.id))
        .where(
            PhysicalPrinterConnector.user_id == user_id,
            PhysicalPrinterConnector.active.is_(True),
            PhysicalPrinterConnector.last_seen_at.is_not(None),
        )
        .scalar_subquery()
    )
    automatic_assignments = (
        select(func.count(MaterialSlotAssignment.id))
        .where(
            MaterialSlotAssignment.user_id == user_id,
            MaterialSlotAssignment.active.is_(True),
            MaterialSlotAssignment.spool_id.is_not(None),
            MaterialSlotAssignment.source.in_(("provider_report", "hh_snapshot")),
        )
        .scalar_subquery()
    )
    assigned_slot_count = (
        select(func.count(distinct(MaterialSlotAssignment.material_slot_id)))
        .join(MaterialSlot, MaterialSlot.id == MaterialSlotAssignment.material_slot_id)
        .where(
            MaterialSlot.material_system_id == MaterialSystem.id,
            MaterialSlot.active.is_(True),
            MaterialSlotAssignment.active.is_(True),
            MaterialSlotAssignment.spool_id.is_not(None),
        )
        .correlate(MaterialSystem)
        .scalar_subquery()
    )
    full_material_systems = (
        select(func.count(MaterialSystem.id))
        .where(
            MaterialSystem.user_id == user_id,
            MaterialSystem.active.is_(True),
            active_slot_count >= 4,
            assigned_slot_count == active_slot_count,
        )
        .scalar_subquery()
    )
    depleted_spools = (
        select(func.count(distinct(PresetUsageEvent.spool_id)))
        .where(
            PresetUsageEvent.user_id == user_id,
            PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
            PresetUsageEvent.spool_id.is_not(None),
            PresetUsageEvent.remaining_weight_g <= 0,
        )
        .scalar_subquery()
    )
    wiki_articles = (
        select(func.count(WikiArticle.id))
        .where(
            WikiArticle.created_by_id == user_id,
            WikiArticle.status == WikiArticleStatus.PUBLISHED,
            WikiArticle.published.is_(True),
        )
        .scalar_subquery()
    )
    wiki_revisions = (
        select(func.count(WikiRevision.id))
        .where(
            WikiRevision.created_by_id == user_id,
            WikiRevision.status == WikiRevisionStatus.PUBLISHED,
            WikiRevision.authorship == WikiRevisionAuthorship.COMMUNITY,
            WikiRevision.base_revision_id.is_not(None),
        )
        .scalar_subquery()
    )
    first_hundred = (
        select(func.count(User.id)).where(User.id == user_id, User.id <= 100).scalar_subquery()
    )

    row = (
        await db.execute(
            select(
                published_presets,
                saved_by_others,
                confirmed_users,
                confirmed_own_prints,
                preset_material_types,
                spools,
                material_systems,
                happy_hare,
                connectors,
                automatic_assignments,
                full_material_systems,
                depleted_spools,
                wiki_articles,
                wiki_revisions,
                first_hundred,
            )
        )
    ).one()
    return AchievementMetrics(*(int(value or 0) for value in row))


def _metric_value(definition: AchievementDefinition, metrics: AchievementMetrics) -> int:
    if definition.metric is None:
        return 0
    return int(getattr(metrics, definition.metric))


async def _threshold_evidence(
    db: AsyncSession, *, user_id: int, definition: AchievementDefinition
) -> tuple[str | None, int | None, datetime | None]:
    """Return the durable row and best reconstructable time for a threshold."""
    if definition.metric == "published_presets":
        occurred_at = func.coalesce(Preset.moderated_at, Preset.updated_at, Preset.created_at)
        row = (
            await db.execute(
                select(Preset.id, occurred_at)
                .where(*_published_preset_filter(user_id))
                .order_by(occurred_at.asc(), Preset.id.asc())
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
    if definition.metric == "confirmed_own_prints":
        row = (
            await db.execute(
                select(PresetUsageEvent.id, PresetUsageEvent.created_at)
                .join(Preset, Preset.id == PresetUsageEvent.preset_id)
                .where(
                    Preset.user_id == user_id,
                    PresetUsageEvent.user_id == user_id,
                    PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                )
                .order_by(PresetUsageEvent.created_at.asc(), PresetUsageEvent.id.asc())
                .limit(1)
            )
        ).first()
        return ("preset_usage", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "preset_material_types":
        occurred_at = func.coalesce(Preset.moderated_at, Preset.updated_at, Preset.created_at)
        rows = (
            await db.execute(
                select(Preset.id, Filament.material_type, occurred_at)
                .join(Filament, Filament.id == Preset.filament_id)
                .where(*_published_preset_filter(user_id))
                .order_by(occurred_at.asc(), Preset.id.asc())
            )
        ).all()
        seen_material_types: set[str] = set()
        for preset_id, material_type, reached_at in rows:
            seen_material_types.add(material_type)
            if len(seen_material_types) >= definition.target:
                return "preset_material_types", int(preset_id), reached_at
        return None, None, None
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
    if definition.metric in {"material_systems", "happy_hare", "full_material_systems"}:
        conditions = [MaterialSystem.user_id == user_id, MaterialSystem.active.is_(True)]
        if definition.metric == "material_systems":
            active_slots = (
                select(func.count(MaterialSlot.id))
                .where(
                    MaterialSlot.material_system_id == MaterialSystem.id,
                    MaterialSlot.active.is_(True),
                )
                .correlate(MaterialSystem)
                .scalar_subquery()
            )
            conditions.append(active_slots >= 2)
        if definition.metric == "happy_hare":
            conditions.append(MaterialSystem.provider == "happy_hare")
        if definition.metric == "full_material_systems":
            active_slots = (
                select(func.count(MaterialSlot.id))
                .where(
                    MaterialSlot.material_system_id == MaterialSystem.id,
                    MaterialSlot.active.is_(True),
                )
                .correlate(MaterialSystem)
                .scalar_subquery()
            )
            assigned_slots = (
                select(func.count(distinct(MaterialSlotAssignment.material_slot_id)))
                .join(MaterialSlot, MaterialSlot.id == MaterialSlotAssignment.material_slot_id)
                .where(
                    MaterialSlot.material_system_id == MaterialSystem.id,
                    MaterialSlot.active.is_(True),
                    MaterialSlotAssignment.active.is_(True),
                    MaterialSlotAssignment.spool_id.is_not(None),
                )
                .correlate(MaterialSystem)
                .scalar_subquery()
            )
            conditions.extend((active_slots >= 4, assigned_slots == active_slots))
        row = (
            await db.execute(
                select(MaterialSystem.id, MaterialSystem.updated_at)
                .where(*conditions)
                .order_by(MaterialSystem.updated_at.asc(), MaterialSystem.id.asc())
                .limit(1)
            )
        ).first()
        return ("material_system", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "connectors":
        row = (
            await db.execute(
                select(PhysicalPrinterConnector.id, PhysicalPrinterConnector.created_at)
                .where(
                    PhysicalPrinterConnector.user_id == user_id,
                    PhysicalPrinterConnector.active.is_(True),
                    PhysicalPrinterConnector.last_seen_at.is_not(None),
                )
                .order_by(
                    PhysicalPrinterConnector.created_at.asc(), PhysicalPrinterConnector.id.asc()
                )
                .limit(1)
            )
        ).first()
        return ("printer_connector", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "automatic_assignments":
        row = (
            await db.execute(
                select(MaterialSlotAssignment.id, MaterialSlotAssignment.created_at)
                .where(
                    MaterialSlotAssignment.user_id == user_id,
                    MaterialSlotAssignment.active.is_(True),
                    MaterialSlotAssignment.spool_id.is_not(None),
                    MaterialSlotAssignment.source.in_(("provider_report", "hh_snapshot")),
                )
                .order_by(MaterialSlotAssignment.created_at.asc(), MaterialSlotAssignment.id.asc())
                .limit(1)
            )
        ).first()
        return ("slot_assignment", int(row[0]), row[1]) if row else (None, None, None)
    if definition.metric == "depleted_spools":
        row = (
            await db.execute(
                select(PresetUsageEvent.id, PresetUsageEvent.created_at)
                .where(
                    PresetUsageEvent.user_id == user_id,
                    PresetUsageEvent.event_type == PresetUsageEventType.printer_report,
                    PresetUsageEvent.spool_id.is_not(None),
                    PresetUsageEvent.remaining_weight_g <= 0,
                )
                .order_by(PresetUsageEvent.created_at.asc(), PresetUsageEvent.id.asc())
                .limit(1)
            )
        ).first()
        return ("preset_usage", int(row[0]), row[1]) if row else (None, None, None)
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
    if definition.metric == "wiki_revisions":
        occurred_at = func.coalesce(WikiRevision.published_at, WikiRevision.updated_at)
        row = (
            await db.execute(
                select(WikiRevision.id, occurred_at)
                .where(
                    WikiRevision.created_by_id == user_id,
                    WikiRevision.status == WikiRevisionStatus.PUBLISHED,
                    WikiRevision.authorship == WikiRevisionAuthorship.COMMUNITY,
                    WikiRevision.base_revision_id.is_not(None),
                )
                .order_by(occurred_at.asc(), WikiRevision.id.asc())
                .offset(definition.target - 1)
                .limit(1)
            )
        ).first()
        return ("wiki_revision", int(row[0]), row[1]) if row else (None, None, None)
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
        source=row.source,
    )


def _contributor_roles(earned_codes: set[str]) -> list[str]:
    roles: list[str] = []
    if FIRST_CATALOG_CONTRIBUTION in earned_codes:
        roles.append("catalog_contributor")
    if FIRST_PROFILE in earned_codes:
        roles.append("preset_author")
    if PRINTER_INTEGRATION_CONNECTED in earned_codes or HAPPY_HARE_CONNECTED in earned_codes:
        roles.append("hardware_integrator")
    if FIRST_WIKI_ARTICLE in earned_codes or FIRST_WIKI_REVISION in earned_codes:
        roles.append("wiki_contributor")
    if SPOOL_COLLECTOR_20 in earned_codes:
        roles.append("collector")
    return roles


def _next_achievement_progress(
    *, earned_codes: set[str], metrics: AchievementMetrics
) -> list[AchievementProgressResponse]:
    next_by_family: dict[str, AchievementProgressResponse] = {}
    for definition in ACHIEVEMENT_DEFINITIONS:
        if (
            definition.code in earned_codes
            or definition.hidden
            or not definition.show_progress
            or definition.award_mode != "automatic"
        ):
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
            .where(UserAchievement.user_id == user_id, UserAchievement.revoked_at.is_(None))
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
    """Return active awards and live factual progress without writes."""
    return await _build_overview(db, user_id=user_id)


async def evaluate_achievement_overview(
    db: AsyncSession, *, user_id: int
) -> AchievementOverviewResponse:
    """Retroactively award every threshold supported by durable current facts."""
    metrics = await _achievement_metrics(db, user_id)
    existing_codes = set(
        await db.scalars(
            select(UserAchievement.code).where(
                UserAchievement.user_id == user_id, UserAchievement.revoked_at.is_(None)
            )
        )
    )
    newly_earned: list[str] = []
    for definition in ACHIEVEMENT_DEFINITIONS:
        if (
            not definition.auto_evaluate
            or definition.award_mode != "automatic"
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
    return await _build_overview(db, user_id=user_id, metrics=metrics, newly_earned=newly_earned)


async def read_admin_achievement_overview(
    db: AsyncSession, *, user_id: int
) -> AdminAchievementOverviewResponse:
    rows = list(
        await db.scalars(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .order_by(UserAchievement.earned_at.desc(), UserAchievement.id.desc())
        )
    )
    achievements: list[AdminAchievementResponse] = []
    for row in rows:
        definition = _DEFINITIONS_BY_CODE.get(row.code)
        achievements.append(
            AdminAchievementResponse(
                code=row.code,
                category=definition.category if definition else "legacy",
                rarity=definition.rarity if definition else "common",
                source=row.source,
                earned_at=row.earned_at,
                awarded_by_user_id=row.awarded_by_user_id,
                award_reason=row.award_reason,
                revoked_at=row.revoked_at,
                revoked_by_user_id=row.revoked_by_user_id,
                revoke_reason=row.revoke_reason,
            )
        )
    return AdminAchievementOverviewResponse(
        achievements=achievements, manual_awardable_codes=list(MANUAL_ACHIEVEMENT_CODES)
    )


async def grant_manual_achievement(
    db: AsyncSession, *, user_id: int, code: str, admin_user_id: int, reason: str
) -> UserAchievement:
    definition = _DEFINITIONS_BY_CODE.get(code)
    if definition is None or definition.award_mode != "manual":
        raise ManualAchievementError(ERR_ACHIEVEMENT_NOT_MANUAL)
    existing = await db.scalar(
        select(UserAchievement).where(
            UserAchievement.user_id == user_id, UserAchievement.code == code
        )
    )
    if existing is not None:
        if existing.revoked_at is not None:
            raise ManualAchievementError(ERR_ACHIEVEMENT_REGRANT_FORBIDDEN)
        raise ManualAchievementError(ERR_ACHIEVEMENT_ALREADY_AWARDED)
    achievement = UserAchievement(
        user_id=user_id,
        code=code,
        source="manual",
        awarded_by_user_id=admin_user_id,
        award_reason=reason.strip(),
        evidence_type="admin_award",
    )
    try:
        async with db.begin_nested():
            db.add(achievement)
            await db.flush()
    except IntegrityError:
        raise ManualAchievementError(ERR_ACHIEVEMENT_ALREADY_AWARDED) from None
    return achievement


async def revoke_manual_achievement(
    db: AsyncSession, *, user_id: int, code: str, admin_user_id: int, reason: str
) -> UserAchievement:
    definition = _DEFINITIONS_BY_CODE.get(code)
    if definition is None or definition.award_mode not in {"manual", "migration"}:
        raise ManualAchievementError(ERR_ACHIEVEMENT_NOT_MANUAL)
    achievement = await db.scalar(
        select(UserAchievement)
        .where(
            UserAchievement.user_id == user_id,
            UserAchievement.code == code,
            UserAchievement.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if achievement is None:
        raise ManualAchievementError(ERR_ACHIEVEMENT_NOT_AWARDED)
    achievement.revoked_at = datetime.now(timezone.utc)
    achievement.revoked_by_user_id = admin_user_id
    achievement.revoke_reason = reason.strip()
    await db.flush()
    return achievement


# Compatibility for internal callers introduced by the first motivation slice.
achievement_overview = evaluate_achievement_overview
