"""Сервис для удаления аккаунта пользователя с обработкой связанных данных."""

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_OWNERSHIP_TRANSFER_REQUIRED,
    ERR_REPRESENTATION_RELEASE_REQUIRED,
    raise_error,
)
from app.models.brand import Brand
from app.models.brand_request import BrandRequest, BrandRequestStatus
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.crm import CrmCustomer, CrmQuote
from app.models.email_communication import EmailThread
from app.models.feedback import Feedback
from app.models.filament_review import FilamentReview
from app.models.orca_slice_report import OrcaSliceReport
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.preset import Preset, PresetModerationStatus
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.models.user import User, UserRole
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.models.wiki_article import WikiArticle
from app.models.wiki_revision import WikiRevision, WikiRevisionReview, WikiRevisionStatus


async def _library_stats(user_id: int, db: AsyncSession) -> dict:
    counts: dict[str, int] = {}
    for key, model, owner in (
        ("spools_count", UserSpool, UserSpool.user_id),
        ("printers_count", UserPrinterDevice, UserPrinterDevice.user_id),
        ("printer_profiles_count", PrinterProfile, PrinterProfile.owner_user_id),
        ("print_profiles_count", PrintProfile, PrintProfile.owner_user_id),
        ("calculations_count", CalculatorHistoryEntry, CalculatorHistoryEntry.user_id),
        ("quotes_count", CrmQuote, CrmQuote.user_id),
        ("customers_count", CrmCustomer, CrmCustomer.user_id),
        ("slice_reports_count", OrcaSliceReport, OrcaSliceReport.user_id),
    ):
        counts[key] = int(
            await db.scalar(select(func.count(model.id)).where(owner == user_id)) or 0
        )
    return counts


async def get_deletion_stats(user_id: int, db: AsyncSession) -> dict:
    """
    Получить статистику данных пользователя перед удалением аккаунта.

    Returns:
        dict: Статистика данных пользователя
    """
    # Количество пресетов пользователя
    presets_result = await db.execute(
        select(func.count(Preset.id)).where(Preset.user_id == user_id)
    )
    presets_count = presets_result.scalar() or 0

    # Количество официальных пресетов
    official_result = await db.execute(
        select(func.count(Preset.id)).where(
            and_(Preset.user_id == user_id, Preset.is_official == True)
        )
    )
    official_presets_count = official_result.scalar() or 0

    # Количество одобренных пресетов
    approved_result = await db.execute(
        select(func.count(Preset.id)).where(
            and_(
                Preset.user_id == user_id,
                Preset.moderation_status == PresetModerationStatus.APPROVED
            )
        )
    )
    approved_presets_count = approved_result.scalar() or 0

    # Количество пресетов, сохраненных другими пользователями
    presets_used_result = await db.execute(
        select(func.count(func.distinct(UserSavedPreset.preset_id)))
        .join(Preset, UserSavedPreset.preset_id == Preset.id)
        .where(
            and_(
                Preset.user_id == user_id,
                UserSavedPreset.user_id != user_id
            )
        )
    )
    presets_used_by_others_count = presets_used_result.scalar() or 0

    # Количество отзывов
    reviews_result = await db.execute(
        select(func.count(FilamentReview.id)).where(FilamentReview.user_id == user_id)
    )
    reviews_count = reviews_result.scalar() or 0

    # Количество сохраненных пресетов (личные закладки)
    saved_presets_result = await db.execute(
        select(func.count(UserSavedPreset.id)).where(UserSavedPreset.user_id == user_id)
    )
    saved_presets_count = saved_presets_result.scalar() or 0

    # Количество заявок на верификацию бренда
    brand_requests_result = await db.execute(
        select(func.count(BrandRequest.id)).where(BrandRequest.user_id == user_id)
    )
    brand_requests_count = brand_requests_result.scalar() or 0

    memberships = (
        await db.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.active.is_(True),
            )
        )
    ).all()
    is_brand_representative = bool(memberships)
    organization_memberships_count = len(memberships)
    owned_organizations_count = sum(
        membership.role == OrganizationMemberRole.OWNER for membership in memberships
    )
    sole_owner_organizations_count = 0
    transfer_required = False
    brand_other_representatives_count = 0
    for membership in memberships:
        other_members = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        brand_other_representatives_count += other_members
        if membership.role == OrganizationMemberRole.OWNER:
            other_owners = int(
                await db.scalar(
                    select(func.count(OrganizationMembership.id)).where(
                        OrganizationMembership.organization_id == membership.organization_id,
                        OrganizationMembership.active.is_(True),
                        OrganizationMembership.role == OrganizationMemberRole.OWNER,
                        OrganizationMembership.id != membership.id,
                    )
                )
                or 0
            )
            if other_owners == 0:
                sole_owner_organizations_count += 1
                transfer_required = transfer_required or other_members > 0

    library = await _library_stats(user_id, db)

    return {
        **library,
        "presets_count": presets_count,
        "official_presets_count": official_presets_count,
        "approved_presets_count": approved_presets_count,
        "presets_used_by_others_count": presets_used_by_others_count,
        "reviews_count": reviews_count,
        "saved_presets_count": saved_presets_count,
        "brand_requests_count": brand_requests_count,
        "is_brand_representative": is_brand_representative,
        "brand_other_representatives_count": brand_other_representatives_count,
        "organization_memberships_count": organization_memberships_count,
        "owned_organizations_count": owned_organizations_count,
        "sole_owner_organizations_count": sole_owner_organizations_count,
        "ownership_transfer_required": transfer_required,
        "representation_release_available": (
            sole_owner_organizations_count > 0 and not transfer_required
        ),
    }


async def delete_user_account(
    user: User,
    delete_reviews: bool,
    release_brand_representation: bool,
    db: AsyncSession,
) -> None:
    """
    Удалить аккаунт пользователя с обработкой связанных данных.

    Args:
        user: Пользователь для удаления
        delete_reviews: True - удалить отзывы полностью, False - анонимизировать
        release_brand_representation: снять официальное представительство у организаций,
            где пользователь является единственным участником-owner
        db: Сессия базы данных
    """
    user_id = user.id

    memberships = (
        await db.scalars(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.active.is_(True),
            )
        )
    ).all()
    organization_ids = sorted({membership.organization_id for membership in memberships})
    if organization_ids:
        # Serialize deletion with role changes/transfers so two owners cannot
        # concurrently leave the same organization without a successor.
        await db.execute(
            select(Organization.id)
            .where(Organization.id.in_(organization_ids))
            .order_by(Organization.id)
            .with_for_update()
        )
        memberships = (
            await db.scalars(
                select(OrganizationMembership)
                .where(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.active.is_(True),
                )
                .order_by(OrganizationMembership.organization_id)
                .with_for_update()
            )
        ).all()
    release_organization_ids: set[int] = set()
    for membership in memberships:
        if membership.role != OrganizationMemberRole.OWNER:
            continue
        other_owners = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.role == OrganizationMemberRole.OWNER,
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        if other_owners > 0:
            continue
        other_members = int(
            await db.scalar(
                select(func.count(OrganizationMembership.id)).where(
                    OrganizationMembership.organization_id == membership.organization_id,
                    OrganizationMembership.active.is_(True),
                    OrganizationMembership.id != membership.id,
                )
            )
            or 0
        )
        if other_members > 0:
            raise_error(409, ERR_OWNERSHIP_TRANSFER_REQUIRED)
        if not release_brand_representation:
            raise_error(409, ERR_REPRESENTATION_RELEASE_REQUIRED)
        release_organization_ids.add(membership.organization_id)

    # 1. Обработка пресетов
    presets_result = await db.execute(
        select(Preset)
        .where(Preset.user_id == user_id)
        .options(selectinload(Preset.saved_by_users))
    )
    presets = presets_result.scalars().all()

    for preset in presets:
        # Что осталось людям — остаётся, но без автора: официальные пресеты и
        # одобренные, которые кто-то уже сохранил себе или использует.
        if preset.is_official or preset.moderation_status == PresetModerationStatus.APPROVED:
            preset.user_id = None

        # Всё прочее — черновики, ожидающие и отклонённые — удаляется. Никто, кроме
        # владельца, их не видел, а оставленные без владельца они становятся
        # недостижимыми навсегда: ни в каталоге, ни в чьём-либо профиле. И это не
        # обезличивание: имя и описание человек писал сам и мог указать там себя.
        else:
            await db.delete(preset)

    # 2. Обработка отзывов
    reviews_result = await db.execute(
        select(FilamentReview).where(FilamentReview.user_id == user_id)
    )
    reviews = reviews_result.scalars().all()

    if delete_reviews:
        for review in reviews:
            await db.delete(review)
    else:
        for review in reviews:
            review.user_id = None

    # 3. Удаление личных закладок (UserSavedPresets)
    saved_presets_result = await db.execute(
        select(UserSavedPreset).where(UserSavedPreset.user_id == user_id)
    )
    saved_presets = saved_presets_result.scalars().all()
    for saved_preset in saved_presets:
        await db.delete(saved_preset)

    # 4. Обработка заявок на верификацию бренда
    brand_requests_result = await db.execute(
        select(BrandRequest).where(BrandRequest.user_id == user_id)
    )
    brand_requests = brand_requests_result.scalars().all()
    for request in brand_requests:
        # Удаляем pending/rejected заявки
        if request.status in [BrandRequestStatus.PENDING, BrandRequestStatus.REJECTED]:
            await db.delete(request)
        # Одобренные заявки оставляем для истории (можно добавить флаг archived)

    # 5. Membership lifecycle. Public brands and their catalog content are
    # never deleted with an account. Explicit release only removes the
    # official verified status; existing QR identifiers stay untouched.
    if release_organization_ids:
        release_brands = (
            await db.scalars(
                select(Brand).where(Brand.organization_id.in_(release_organization_ids))
            )
        ).all()
        for brand in release_brands:
            brand.verified = False
    for membership in memberships:
        membership.active = False
    user.brand_id = None
    if user.role == UserRole.BRAND:
        user.role = UserRole.USER

    # Private Wiki work is owned user data. Remove unpublished articles and
    # non-published revisions; preserve published knowledge without personal
    # attribution so public history remains intact.
    private_article_ids = (
        await db.scalars(
            select(WikiArticle.id).where(
                WikiArticle.created_by_id == user_id,
                WikiArticle.published_revision_id.is_(None),
            )
        )
    ).all()
    if private_article_ids:
        await db.execute(
            delete(WikiArticle).where(WikiArticle.id.in_(private_article_ids))
        )

    await db.execute(
        delete(WikiRevision).where(
            WikiRevision.created_by_id == user_id,
            WikiRevision.status != WikiRevisionStatus.PUBLISHED,
        )
    )
    await db.execute(
        update(WikiArticle)
        .where(WikiArticle.created_by_id == user_id)
        .values(created_by_id=None, author=None)
    )
    await db.execute(
        update(WikiArticle)
        .where(WikiArticle.updated_by_id == user_id)
        .values(updated_by_id=None)
    )
    await db.execute(
        update(WikiArticle)
        .where(WikiArticle.reviewed_by_id == user_id)
        .values(reviewed_by_id=None)
    )
    await db.execute(
        update(WikiRevision)
        .where(WikiRevision.created_by_id == user_id)
        .values(created_by_id=None)
    )
    await db.execute(
        update(WikiRevision)
        .where(WikiRevision.reviewed_by_id == user_id)
        .values(reviewed_by_id=None)
    )
    await db.execute(
        update(WikiRevisionReview)
        .where(WikiRevisionReview.reviewer_id == user_id)
        .values(reviewer_id=None)
    )

    threads = (
        await db.scalars(
            select(EmailThread).where(
                func.lower(EmailThread.participant_email) == user.email.lower()
            )
        )
    ).all()
    for thread in threads:
        await db.delete(thread)

    await db.execute(
        update(Feedback)
        .where(func.lower(Feedback.email) == user.email.lower())
        .values(email=None)
    )

    await db.delete(user)

    await db.commit()
