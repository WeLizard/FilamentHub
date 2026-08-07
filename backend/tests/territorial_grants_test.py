"""Один бренд, одни филаменты, представители разных стран.

Ради этого сценария вся затея и была: Creality существует один, а Creality
Russia и Creality Germany входят в него, каждый со своей областью.
"""

import pytest
from httpx import AsyncClient
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
