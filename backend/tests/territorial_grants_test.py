"""Один бренд, одни филаменты, представители разных стран.

Ради этого сценария вся затея и была: Creality существует один, а Creality
Russia и Creality Germany входят в него, каждый со своей областью.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.filament import Filament
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.user import User, UserRole
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)


async def _representative(
    db: AsyncSession,
    brand: Brand,
    slug: str,
    country: str | None,
    *,
    status: GrantStatus = GrantStatus.active,
    source: GrantSource = GrantSource.invitation,
    owns_workspace: bool = False,
) -> dict[str, str]:
    """Организация, её сотрудник и право на бренд. Возвращает заголовки входа."""
    organization = Organization(name=f"Org {slug}", slug=f"org-{slug}")
    db.add(organization)
    await db.flush()

    user = User(
        email=f"{slug}@example.com",
        username=f"user_{slug}",
        password_hash=get_password_hash("testpassword123"),
        role=UserRole.USER,
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.flush()

    db.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        )
    )
    # Мастерская бренда одна: приглашать в команду может только её владелец.
    if owns_workspace:
        brand.organization_id = organization.id
        brand.verified = True

    db.add(
        BrandTerritorialGrant(
            brand_id=brand.id,
            organization_id=organization.id,
            country=country,
            status=status,
            source=source,
        )
    )
    await db.commit()

    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def _outsider(db: AsyncSession, slug: str) -> tuple[User, dict[str, str]]:
    """Человек со стороны: ни организации, ни прав на бренд."""
    user = User(
        email=f"{slug}@example.com",
        username=f"user_{slug}",
        password_hash=get_password_hash("testpassword123"),
        role=UserRole.USER,
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def _brand_with_one_filament(db: AsyncSession) -> tuple[Brand, Filament]:
    brand = Brand(name="TestBrand Grants", slug="testbrand-grants", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="TestBrand PLA",
        slug="testbrand-pla-grants",
        material_type="PLA",
        price_per_kg=1500,
        diameter=1.75,
        density=1.24,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(brand)
    await db.refresh(filament)
    return brand, filament


@pytest.mark.asyncio
async def test_each_representative_manages_only_their_own_country(
    client: AsyncClient, db_session: AsyncSession
):
    """Русский ведёт Россию, немец — Германию, и в чужую страну не заходит."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-rep", "RU")
    germany = await _representative(db_session, brand, "de-rep", "DE")

    mine = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=russia,
        json={"country": "RU", "price": 1490, "currency": "RUB", "published": True},
    )
    assert mine.status_code == 201

    theirs = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=russia,
        json={"country": "DE", "price": 24.9, "currency": "EUR"},
    )
    assert theirs.status_code == 403

    german_cell = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=germany,
        json={"country": "DE", "price": 24.9, "currency": "EUR", "published": True},
    )
    assert german_cell.status_code == 201

    # И правку чужой ячейки тоже не пускает.
    intrusion = await client.patch(
        f"/api/v1/filaments/{filament.id}/country-cells/DE",
        headers=russia,
        json={"price": 1, "currency": "EUR"},
    )
    assert intrusion.status_code == 403


@pytest.mark.asyncio
async def test_both_work_on_the_same_product_without_cloning_it(
    client: AsyncClient, db_session: AsyncSession
):
    """Товар остаётся один: страна не создаёт копию."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-same", "RU")
    germany = await _representative(db_session, brand, "de-same", "DE")

    await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=russia,
        json={"country": "RU", "price": 1490, "currency": "RUB", "published": True},
    )
    await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=germany,
        json={"country": "DE", "price": 24.9, "currency": "EUR", "published": True},
    )

    catalogue = await client.get("/api/v1/filaments/?search=TestBrand PLA&size=100")
    matching = [item for item in catalogue.json()["items"] if item["id"] == filament.id]
    assert len(matching) == 1

    russian_view = await client.get(f"/api/v1/filaments/{filament.id}?country=RU")
    german_view = await client.get(f"/api/v1/filaments/{filament.id}?country=DE")
    assert russian_view.json()["id"] == german_view.json()["id"] == filament.id
    assert russian_view.json()["price_per_kg"] == 1490
    assert german_view.json()["price_per_kg"] == 24.9


@pytest.mark.asyncio
async def test_a_country_representative_does_not_touch_the_common_layer(
    client: AsyncClient, db_session: AsyncSession
):
    """Свойства пластика одни на весь мир и из страны не переписываются."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-common", "RU")

    common = await client.patch(
        f"/api/v1/filaments/{filament.id}", headers=russia, json={"density": 9.9}
    )
    assert common.status_code == 403

    brand_common = await client.patch(
        f"/api/v1/brands/{brand.id}", headers=russia, json={"website": "https://hijacked.example"}
    )
    assert brand_common.status_code in (403, 404)

    await db_session.refresh(filament)
    assert filament.density == 1.24


@pytest.mark.asyncio
async def test_a_global_representative_reaches_every_country(
    client: AsyncClient, db_session: AsyncSession
):
    """Глобальная область покрывает любую страну — но её выдают, а не берут."""
    brand, filament = await _brand_with_one_filament(db_session)
    global_rep = await _representative(db_session, brand, "global-rep", None)

    for country in ("RU", "DE", "BR"):
        created = await client.post(
            f"/api/v1/filaments/{filament.id}/country-cells",
            headers=global_rep,
            json={"country": country, "published": True},
        )
        assert created.status_code == 201


@pytest.mark.asyncio
async def test_a_grant_only_counts_once_it_is_approved(
    client: AsyncClient, db_session: AsyncSession
):
    """Поданная заявка правами не является, пока её не одобрили."""
    brand, filament = await _brand_with_one_filament(db_session)
    applicant = await _representative(
        db_session, brand, "applicant", "RU", status=GrantStatus.pending,
        source=GrantSource.application,
    )

    too_early = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=applicant,
        json={"country": "RU"},
    )
    assert too_early.status_code == 403


@pytest.mark.asyncio
async def test_a_revoked_grant_stops_working(client: AsyncClient, db_session: AsyncSession):
    """Отозванное право перестаёт действовать сразу."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-revoked", "RU")

    allowed = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=russia,
        json={"country": "RU", "published": True},
    )
    assert allowed.status_code == 201

    grant = await db_session.scalar(
        select(BrandTerritorialGrant).where(BrandTerritorialGrant.brand_id == brand.id)
    )
    grant.status = GrantStatus.revoked
    grant.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()

    denied = await client.patch(
        f"/api/v1/filaments/{filament.id}/country-cells/RU",
        headers=russia,
        json={"published": False},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_an_outsider_manages_nothing(client: AsyncClient, db_session: AsyncSession):
    """Обычный человек ячейками не распоряжается."""
    brand, filament = await _brand_with_one_filament(db_session)
    stranger = await _representative(db_session, brand, "stranger", "RU")
    other_brand = Brand(name="Someone Else", slug="someone-else", active=True)
    db_session.add(other_brand)
    await db_session.flush()
    other_filament = Filament(
        brand_id=other_brand.id, name="Other PLA", slug="other-pla-grants", material_type="PLA"
    )
    db_session.add(other_filament)
    await db_session.commit()
    await db_session.refresh(other_filament)

    # Право выдано на свой бренд, а не на чужой.
    denied = await client.post(
        f"/api/v1/filaments/{other_filament.id}/country-cells",
        headers=stranger,
        json={"country": "RU"},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_an_application_names_its_country_and_approval_grants_it(
    client: AsyncClient, admin_client: AsyncClient, db_session: AsyncSession
):
    """Заявитель называет страну сам; одобрение превращает её в право."""
    from sqlalchemy import select

    from app.models.brand_request import BrandRequest
    from app.models.organization import Organization, OrganizationMembership

    brand = Brand(name="Applied Brand", slug="applied-brand", active=True)
    db_session.add(brand)
    await db_session.flush()

    organization = Organization(name="Applicant Org", slug="applicant-org")
    db_session.add(organization)
    await db_session.flush()

    applicant = User(
        email="claimant@example.com",
        username="claimant",
        password_hash=get_password_hash("testpassword123"),
        role=UserRole.USER,
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(applicant)
    await db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=applicant.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        )
    )
    request = BrandRequest(
        user_id=applicant.id,
        request_type="join",
        brand_id=brand.id,
        country="RU",
        status="pending",
    )
    db_session.add(request)
    await db_session.commit()
    await db_session.refresh(request)

    approved = await admin_client.patch(
        f"/api/v1/admin/brand-requests/{request.id}", json={"status": "approved"}
    )
    assert approved.status_code == 200

    grant = await db_session.scalar(
        select(BrandTerritorialGrant).where(BrandTerritorialGrant.brand_id == brand.id)
    )
    assert grant is not None
    assert grant.country == "RU"
    assert grant.status == GrantStatus.active
    assert grant.source == GrantSource.application


@pytest.mark.asyncio
async def test_the_representative_is_told_where_their_area_ends(
    client: AsyncClient, db_session: AsyncSession
):
    """Границу объясняют словами, а не заблокированным полем."""
    brand, _ = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-panel", "RU")

    answer = await client.get(f"/api/v1/brands/{brand.id}/my-territories", headers=russia)
    assert answer.status_code == 200
    told = answer.json()

    assert [t["country"] for t in told["territories"]] == ["RU"]
    # Общий слой закрыт, и интерфейсу есть что сказать вместо «поле недоступно».
    assert told["can_edit_common"] is False
    assert told["is_admin"] is False


@pytest.mark.asyncio
async def test_a_representative_reads_back_their_own_draft(
    client: AsyncClient, db_session: AsyncSession
):
    """Черновик нужно видеть, иначе его нельзя ни доделать, ни опубликовать позже."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-draft", "RU")
    germany = await _representative(db_session, brand, "de-draft", "DE")

    created = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=russia,
        json={"country": "RU", "price": 1490, "currency": "RUB", "published": False},
    )
    assert created.status_code == 201

    mine = await client.get(f"/api/v1/filaments/{filament.id}/country-cells", headers=russia)
    assert [cell["country"] for cell in mine.json()] == ["RU"]

    # Чужой черновик остаётся скрытым: невидимость касается посторонних, а не автора.
    theirs = await client.get(f"/api/v1/filaments/{filament.id}/country-cells", headers=germany)
    assert theirs.json() == []

    stranger = await client.get(f"/api/v1/filaments/{filament.id}/country-cells")
    assert stranger.json() == []


@pytest.mark.asyncio
async def test_a_representative_is_a_separate_company_not_an_employee(
    client: AsyncClient, db_session: AsyncSession
):
    """Головной офис зовёт компанию на страну, и она не входит в его организацию."""
    brand, filament = await _brand_with_one_filament(db_session)
    headquarters = await _representative(db_session, brand, "hq", None, owns_workspace=True)
    _, guest = await _outsider(db_session, "kz-company")
    await db_session.refresh(brand)
    headquarters_organization_id = brand.organization_id

    invited = await client.post(
        f"/api/v1/brands/{brand.id}/representatives/invites",
        headers=headquarters,
        json={
            "email": "kz-company@example.com",
            "country": "KZ",
            "organization_name": "TestBrand Kazakhstan",
            "send_email": False,
        },
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["invite_url"].rsplit("/", 1)[-1]

    accepted = await client.post(f"/api/v1/brand-invites/{token}/accept", headers=guest, json={})
    assert accepted.status_code == 200, accepted.text
    representative_organization_id = accepted.json()["organization_id"]

    # Главный инвариант: своя организация, не организация головного офиса.
    assert representative_organization_id != headquarters_organization_id

    # Казахстан открыт.
    allowed = await client.post(
        f"/api/v1/filaments/{filament.id}/country-cells",
        headers=guest,
        json={"country": "KZ", "price": 9900, "currency": "KZT", "published": True},
    )
    assert allowed.status_code == 201, allowed.text

    # Соседняя страна — нет.
    assert (
        await client.post(
            f"/api/v1/filaments/{filament.id}/country-cells",
            headers=guest,
            json={"country": "UZ", "price": 100, "currency": "UZS"},
        )
    ).status_code == 403

    # Общий слой бренда и общий слой товара — тоже нет.
    assert (
        await client.patch(f"/api/v1/brands/{brand.id}", headers=guest, json={"website": "https://kz.example"})
    ).status_code in (403, 404)
    assert (
        await client.patch(f"/api/v1/filaments/{filament.id}", headers=guest, json={"density": 9.9})
    ).status_code in (403, 404)

    # Отзыв действует сразу, без отложенных задач.
    territories = await client.get(
        f"/api/v1/brands/{brand.id}/representatives", headers=headquarters
    )
    assert territories.status_code == 200, territories.text
    grant_id = next(
        item["grant_id"] for item in territories.json() if item["country"] == "KZ"
    )
    revoked = await client.delete(
        f"/api/v1/brands/{brand.id}/representatives/{grant_id}", headers=headquarters
    )
    assert revoked.status_code == 204

    assert (
        await client.patch(
            f"/api/v1/filaments/{filament.id}/country-cells/KZ",
            headers=guest,
            json={"price": 1},
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_a_territory_invitation_never_reuses_the_brand_organization(
    client: AsyncClient, db_session: AsyncSession
):
    """Старый откат на организацию бренда для этого сценария запрещён.

    Именно он раздал бы приглашённому глобальные права головного офиса вместо
    названной страны, поэтому проверяется отдельно от прав.
    """
    brand, _ = await _brand_with_one_filament(db_session)
    headquarters = await _representative(db_session, brand, "hq-reuse", None, owns_workspace=True)
    guest_user, guest = await _outsider(db_session, "uz-company")
    await db_session.refresh(brand)
    headquarters_organization_id = brand.organization_id
    assert headquarters_organization_id is not None

    invited = await client.post(
        f"/api/v1/brands/{brand.id}/representatives/invites",
        headers=headquarters,
        json={
            "email": "uz-company@example.com",
            "country": "UZ",
            "organization_name": "TestBrand Uzbekistan",
            "send_email": False,
        },
    )
    token = invited.json()["invite_url"].rsplit("/", 1)[-1]
    accepted = await client.post(f"/api/v1/brand-invites/{token}/accept", headers=guest, json={})
    assert accepted.status_code == 200, accepted.text

    await db_session.refresh(brand)
    # Бренд остался за головным офисом: приглашение его мастерскую не перевесило.
    assert brand.organization_id == headquarters_organization_id
    assert accepted.json()["organization_id"] != headquarters_organization_id

    # И сотрудником головного офиса приглашённый не стал.
    in_headquarters = await db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == headquarters_organization_id,
            OrganizationMembership.user_id == guest_user.id,
        )
    )
    assert in_headquarters is None
