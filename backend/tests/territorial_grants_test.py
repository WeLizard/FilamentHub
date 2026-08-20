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
from app.models.filament_analytics_event import FilamentAnalyticsEvent
from app.models.filament_country_cell import FilamentCountryCell
from app.models.notification import Notification
from app.models.organization import (
    Organization,
    OrganizationMemberRole,
    OrganizationMembership,
)
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User, UserRole
from app.services.email_service import EmailSendResult
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

    user.brand_id = brand.id
    user.active_organization_id = organization.id

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
async def test_community_preset_is_open_to_every_user_but_official_status_is_not(
    client: AsyncClient, db_session: AsyncSession
):
    """Company membership is never a prerequisite for a community preset."""
    _, filament = await _brand_with_one_filament(db_session)
    _, ordinary_user = await _outsider(db_session, "community-preset")
    payload = {
        "filament_id": filament.id,
        "name": "Community PLA profile",
        "extruder_temp": 210,
        "bed_temp": 60,
        "is_official": False,
    }

    created = await client.post("/api/v1/presets/", headers=ordinary_user, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["is_official"] is False

    forbidden = await client.post(
        "/api/v1/presets/",
        headers=ordinary_user,
        json={**payload, "name": "Fake official profile", "is_official": True},
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_official_preset_is_managed_by_the_contributing_organization(
    client: AsyncClient, db_session: AsyncSession
):
    """A colleague edits the shared asset; a personal creator account is not the owner."""
    brand, filament = await _brand_with_one_filament(db_session)
    owner_headers = await _representative(
        db_session,
        brand,
        "preset-org-owner",
        "KZ",
        owns_workspace=True,
    )
    owner = await db_session.scalar(
        select(User).where(User.email == "preset-org-owner@example.com")
    )
    assert owner is not None and owner.active_organization_id is not None

    colleague = User(
        email="preset-org-colleague@example.com",
        username="user_preset_org_colleague",
        password_hash=get_password_hash("testpassword123"),
        role=UserRole.USER,
        active=True,
        email_verified=True,
        brand_id=brand.id,
        active_organization_id=owner.active_organization_id,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(colleague)
    await db_session.flush()
    db_session.add(
        OrganizationMembership(
            organization_id=owner.active_organization_id,
            user_id=colleague.id,
            role=OrganizationMemberRole.EDITOR,
            active=True,
            all_brands=True,
        )
    )
    await db_session.commit()
    colleague_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': colleague.email})}"
    }

    created = await client.post(
        "/api/v1/presets/",
        headers=owner_headers,
        json={
            "filament_id": filament.id,
            "name": "Official KZ profile",
            "extruder_temp": 215,
            "bed_temp": 60,
            "is_official": True,
        },
    )
    assert created.status_code == 201, created.text
    preset_id = created.json()["id"]
    assert created.json()["organization_id"] == owner.active_organization_id

    edited = await client.patch(
        f"/api/v1/presets/{preset_id}",
        headers=colleague_headers,
        json={"description": "Maintained by the organization team"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["description"] == "Maintained by the organization team"
    assert edited.json()["organization_id"] == owner.active_organization_id


@pytest.mark.asyncio
async def test_revoked_grant_cannot_activate_a_staged_official_draft(
    client: AsyncClient, db_session: AsyncSession
):
    """Official provenance is not a cached capability after authority is revoked."""
    brand, filament = await _brand_with_one_filament(db_session)
    headers = await _representative(
        db_session,
        brand,
        "revoked-official-draft",
        "KZ",
        owns_workspace=True,
    )
    _, outsider_headers = await _outsider(db_session, "revoked-official-outsider")
    owner = await db_session.scalar(
        select(User).where(User.email == "revoked-official-draft@example.com")
    )
    assert owner is not None and owner.active_organization_id is not None
    draft = Preset(
        user_id=owner.id,
        organization_id=owner.active_organization_id,
        name="Staged official profile",
        extruder_temp=215,
        bed_temp=60,
        is_official=True,
        active=False,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"service_token": "private-staged-token"},
    )
    db_session.add(draft)
    await db_session.flush()
    grant = await db_session.scalar(
        select(BrandTerritorialGrant).where(
            BrandTerritorialGrant.brand_id == brand.id,
            BrandTerritorialGrant.organization_id == owner.active_organization_id,
        )
    )
    assert grant is not None
    grant.status = GrantStatus.revoked
    await db_session.commit()

    activated = await client.post(
        f"/api/v1/presets/{draft.id}/activate",
        headers=headers,
        json={"filament_id": filament.id},
    )

    assert activated.status_code == 403
    await db_session.refresh(draft)
    assert draft.active is False
    assert draft.filament_id is None
    assert draft.orcaslicer_settings["service_token"] == "private-staged-token"
    assert (
        await client.get(
            f"/api/v1/presets/{draft.id}/versions",
            headers=outsider_headers,
        )
    ).status_code == 403


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
async def test_a_country_representative_controls_filament_common_data_until_global_exists(
    client: AsyncClient, db_session: AsyncSession
):
    """Without a global holder, a verified regional organization maintains shared data."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-common", "RU")
    brand.website = "https://original.example"
    await db_session.commit()

    common = await client.patch(
        f"/api/v1/filaments/{filament.id}", headers=russia, json={"density": 9.9}
    )
    assert common.status_code == 200

    # Brand identity remains protected by its separate authority model.
    brand_common = await client.patch(
        f"/api/v1/brands/{brand.id}", headers=russia, json={"website": "https://hijacked.example"}
    )
    assert brand_common.status_code == 403

    await db_session.refresh(filament)
    assert filament.density == 9.9

    await _representative(db_session, brand, "global-common", None)
    protected = await client.patch(
        f"/api/v1/filaments/{filament.id}", headers=russia, json={"density": 8.8}
    )
    assert protected.status_code == 403
    gap = await client.patch(
        f"/api/v1/filaments/{filament.id}",
        headers=russia,
        json={"empty_spool_weight_g": 240},
    )
    assert gap.status_code == 200


@pytest.mark.asyncio
async def test_regional_creation_writes_one_catalog_item_and_its_country_cell(
    client: AsyncClient, db_session: AsyncSession
):
    """The regional create flow is atomic and provenance never becomes ownership."""
    brand, original = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-create", "RU")

    denied = await client.post(
        "/api/v1/filaments/",
        headers=russia,
        json={
            "brand_id": brand.id,
            "name": "Regional PLA DE",
            "material_type": "PLA",
            "country_cell": {
                "country": "DE",
                "price": 20,
                "currency": "EUR",
                "published": True,
            },
        },
    )
    assert denied.status_code == 403
    assert await db_session.scalar(
        select(Filament.id).where(Filament.name == "Regional PLA DE")
    ) is None

    created = await client.post(
        "/api/v1/filaments/",
        headers=russia,
        json={
            "brand_id": brand.id,
            "name": "Regional PLA RU",
            "material_type": "PLA",
            "color_name": "Красный",
            "country_cell": {
                "country": "RU",
                "availability": "available",
                "price": 1490,
                "currency": "RUB",
                "market_color_name": "Красный",
                "published": True,
            },
        },
    )
    assert created.status_code == 201, created.text
    created_id = created.json()["id"]
    cell = await db_session.scalar(
        select(FilamentCountryCell).where(
            FilamentCountryCell.filament_id == created_id,
            FilamentCountryCell.country == "RU",
        )
    )
    assert cell is not None
    assert cell.price == 1490

    # Until a global holder appears, the representative maintains the shared
    # layer even though this record is organization-contributed catalogue data.
    common_edit = await client.patch(
        f"/api/v1/filaments/{created_id}",
        headers=russia,
        json={"density": 9.9},
    )
    assert common_edit.status_code == 200
    overwrite = await client.patch(
        f"/api/v1/filaments/{created_id}",
        headers=russia,
        json={"density": 8.8},
    )
    assert overwrite.status_code == 200
    assert original.id != created_id


@pytest.mark.asyncio
async def test_active_workspace_keeps_rights_and_provenance_in_one_organization(
    client: AsyncClient, db_session: AsyncSession
):
    """A user in two companies cannot combine one's scope with the other's identity."""
    brand, existing_filament = await _brand_with_one_filament(db_session)
    user, headers = await _outsider(db_session, "two-workspaces")
    kz_org = Organization(name="KZ Workspace", slug="kz-workspace")
    de_org = Organization(name="DE Workspace", slug="de-workspace")
    db_session.add_all([kz_org, de_org])
    await db_session.flush()

    db_session.add_all([
        OrganizationMembership(
            organization_id=kz_org.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        ),
        OrganizationMembership(
            organization_id=de_org.id,
            user_id=user.id,
            role=OrganizationMemberRole.OWNER,
            active=True,
            all_brands=True,
        ),
        BrandTerritorialGrant(
            brand_id=brand.id,
            organization_id=kz_org.id,
            country="KZ",
            status=GrantStatus.active,
            source=GrantSource.invitation,
        ),
        BrandTerritorialGrant(
            brand_id=brand.id,
            organization_id=de_org.id,
            country="DE",
            status=GrantStatus.active,
            source=GrantSource.invitation,
        ),
    ])
    user.brand_id = brand.id
    user.active_organization_id = kz_org.id
    await db_session.commit()

    wrong_scope = await client.post(
        f"/api/v1/filaments/{existing_filament.id}/country-cells",
        headers=headers,
        json={"country": "DE", "availability": "available"},
    )
    assert wrong_scope.status_code == 403

    kz_created = await client.post(
        "/api/v1/filaments/",
        headers=headers,
        json={
            "brand_id": brand.id,
            "name": "Workspace KZ PLA",
            "material_type": "PLA",
            "country_cell": {"country": "KZ", "availability": "available"},
        },
    )
    assert kz_created.status_code == 201, kz_created.text
    assert kz_created.json()["contributed_by_organization_id"] == kz_org.id

    switched = await client.put(
        "/api/v1/auth/me/active-brand",
        headers=headers,
        json={"brand_id": brand.id, "organization_id": de_org.id},
    )
    assert switched.status_code == 200, switched.text

    de_created = await client.post(
        "/api/v1/filaments/",
        headers=headers,
        json={
            "brand_id": brand.id,
            "name": "Workspace DE PLA",
            "material_type": "PLA",
            "country_cell": {"country": "DE", "availability": "available"},
        },
    )
    assert de_created.status_code == 201, de_created.text
    assert de_created.json()["contributed_by_organization_id"] == de_org.id


@pytest.mark.asyncio
async def test_analytics_follow_grant_countries_not_the_organization_that_recorded_them(
    client: AsyncClient, db_session: AsyncSession
):
    """Global sees all; every organization for RU sees the same RU slice only."""
    brand, filament = await _brand_with_one_filament(db_session)
    russia = await _representative(db_session, brand, "ru-analytics", "RU")
    russia_two = await _representative(db_session, brand, "ru2-analytics", "RU")
    germany = await _representative(db_session, brand, "de-analytics", "DE")
    global_rep = await _representative(db_session, brand, "global-analytics", None)

    filament.scans_count = 4
    db_session.add_all([
        FilamentAnalyticsEvent(filament_id=filament.id, event_type="qr_scan", country="RU"),
        FilamentAnalyticsEvent(filament_id=filament.id, event_type="qr_scan", country="RU"),
        FilamentAnalyticsEvent(filament_id=filament.id, event_type="qr_scan", country="DE"),
    ])
    await db_session.commit()

    ru_data = (await client.get(
        f"/api/v1/brands/{brand.id}/analytics", headers=russia
    )).json()
    ru_two_data = (await client.get(
        f"/api/v1/brands/{brand.id}/analytics", headers=russia_two
    )).json()
    de_data = (await client.get(
        f"/api/v1/brands/{brand.id}/analytics", headers=germany
    )).json()
    global_data = (await client.get(
        f"/api/v1/brands/{brand.id}/analytics", headers=global_rep
    )).json()

    assert ru_data["scope"] == "territorial"
    assert ru_data["total_scans"] == ru_two_data["total_scans"] == 2
    assert de_data["total_scans"] == 1
    assert global_data["scope"] == "global"
    assert global_data["total_scans"] == 4
    assert global_data["historical_unattributed_scans"] == 1


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
        request_type="representative",
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
    # No global holder exists yet, so the regional workspace maintains the
    # shared material layer while brand identity itself remains protected.
    assert told["can_edit_common"] is False
    assert told["can_edit_filament_common"] is True
    assert told["is_admin"] is False


@pytest.mark.asyncio
async def test_only_a_brand_representative_can_request_a_catalogue_correction(
    client: AsyncClient, db_session: AsyncSession
):
    """The request mails brand representatives, so it stays inside the brand's team.

    A regional representative who cannot edit shared values asks whoever holds
    them; an outsider has the public feedback channel instead.
    """
    brand, filament = await _brand_with_one_filament(db_session)
    await _representative(db_session, brand, "global-correction", None)
    global_user = await db_session.scalar(
        select(User).where(User.email == "global-correction@example.com")
    )
    assert global_user is not None
    requester = await _representative(db_session, brand, "regional-requester", "DE")

    admin, _ = await _outsider(db_session, "correction-admin")
    admin.role = UserRole.ADMIN
    _, outsider = await _outsider(db_session, "correction-outsider")
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/filaments/{filament.id}/common-edit-request",
        headers=outsider,
        json={"message": "The manufacturer's datasheet lists a different density."},
    )
    assert refused.status_code == 403, refused.text

    response = await client.post(
        f"/api/v1/filaments/{filament.id}/common-edit-request",
        headers=requester,
        json={"message": "The manufacturer's datasheet lists a different density."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["recipients"] == 1
    recipients = set(
        await db_session.scalars(
            select(Notification.user_id).where(
                Notification.title == "filament_common_edit_requested"
            )
        )
    )
    assert recipients == {global_user.id}
    assert admin.id not in recipients


@pytest.mark.asyncio
async def test_catalogue_correction_falls_back_to_moderation_without_responsible_org(
    client: AsyncClient, db_session: AsyncSession
):
    brand, filament = await _brand_with_one_filament(db_session)
    admin, _ = await _outsider(db_session, "fallback-admin")
    admin.role = UserRole.ADMIN
    requester = await _representative(db_session, brand, "fallback-requester", "DE")
    await db_session.commit()

    response = await client.post(
        f"/api/v1/filaments/{filament.id}/common-edit-request",
        headers=requester,
        json={"message": "Please verify the material name against the packaging."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["recipients"] == 1
    recipient = await db_session.scalar(
        select(Notification.user_id).where(
            Notification.title == "filament_common_edit_requested"
        )
    )
    assert recipient == admin.id


@pytest.mark.asyncio
async def test_community_record_correction_reaches_regional_rep_when_no_global_holder(
    client: AsyncClient, db_session: AsyncSession
):
    brand, filament = await _brand_with_one_filament(db_session)
    await _representative(db_session, brand, "regional-correction", "DE")
    representative = await db_session.scalar(
        select(User).where(User.email == "regional-correction@example.com")
    )
    assert representative is not None

    admin, _ = await _outsider(db_session, "regional-correction-admin")
    admin.role = UserRole.ADMIN
    requester = await _representative(db_session, brand, "regional-correction-asker", "FR")
    await db_session.commit()

    response = await client.post(
        f"/api/v1/filaments/{filament.id}/common-edit-request",
        headers=requester,
        json={"message": "Please verify the density on this community-created record."},
    )

    assert response.status_code == 200, response.text
    assert response.json()["recipients"] == 1
    recipients = set(
        await db_session.scalars(
            select(Notification.user_id).where(
                Notification.title == "filament_common_edit_requested"
            )
        )
    )
    assert recipients == {representative.id}
    assert admin.id not in recipients


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
        json={"country": "RU"},
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
    guest_user, guest = await _outsider(db_session, "kz-company")
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

    # Регионал обогащает пустые общие данные, но не перезаписывает уже
    # заполненный общий слой. Рыночные поля при этом остаются в ячейке страны.
    assert (
        await client.patch(f"/api/v1/brands/{brand.id}", headers=guest, json={"website": "https://kz.example"})
    ).status_code == 200
    assert (
        await client.patch(f"/api/v1/brands/{brand.id}", headers=guest, json={"website": "https://overwrite.example"})
    ).status_code == 403
    assert (
        await client.patch(f"/api/v1/filaments/{filament.id}", headers=guest, json={"empty_spool_weight_g": 240})
    ).status_code == 200
    assert (
        await client.patch(f"/api/v1/filaments/{filament.id}", headers=guest, json={"empty_spool_weight_g": 241})
    ).status_code == 403

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

    await db_session.refresh(guest_user)
    assert guest_user.brand_id is None
    assert guest_user.active_organization_id is None

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


@pytest.mark.asyncio
async def test_admin_can_send_a_preapproved_country_invitation(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    """The administrator's country invitation is usable without a second review."""
    brand, _ = await _brand_with_one_filament(db_session)
    monkeypatch.setattr(
        "app.api.v1.endpoints.brand_invites.send_brand_invite_email",
        lambda **_: EmailSendResult(sent=True, provider_message_id="test-invite"),
    )

    response = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={
            "email": "country-invite@example.com",
            "target_type": "existing",
            "brand_id": brand.id,
            "country": "kz",
            "language": "ru",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["country"] == "KZ"
    assert response.json()["purpose"] == "territory"
    assert response.json()["pre_verified"] is True
    assert response.json()["send_status"] == "sent"
