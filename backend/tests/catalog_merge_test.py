"""Folding duplicate brands and filaments into the records that stay."""

from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401
from app.core.security import create_access_token, get_password_hash
from app.db.base import Base
from app.models.brand import Brand
from app.models.brand_country_cell import BrandCountryCell
from app.models.brand_monthly_analytics_release import BrandMonthlyAnalyticsRelease
from app.models.brand_territorial_grant import BrandTerritorialGrant, GrantSource, GrantStatus
from app.models.filament import Filament
from app.models.filament_country_cell import CountryAvailability, FilamentCountryCell
from app.models.filament_line import FilamentLine
from app.models.filament_review import FilamentReview
from app.models.organization import Organization, OrganizationMemberRole, OrganizationMembership
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool
from app.services.catalog_merge_service import (
    BRAND_REFERENCES,
    FILAMENT_REFERENCES,
    WEIGHTED_PRESET_REFERENCES,
    merge_filaments,
)
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)


def _references_to(table: str) -> set[str]:
    return {
        f"{column.table.name}.{column.name}"
        for metadata_table in Base.metadata.tables.values()
        for column in metadata_table.columns
        for foreign_key in column.foreign_keys
        if foreign_key.column.table.name == table
    }


def test_merge_handles_every_reference_to_a_merged_record() -> None:
    # A new table pointing at brands, filaments or presets must be taught to
    # the merge; otherwise its rows are orphaned or block the delete.
    assert _references_to("filaments") == FILAMENT_REFERENCES
    assert _references_to("brands") == BRAND_REFERENCES
    assert _references_to("presets") == WEIGHTED_PRESET_REFERENCES


async def _filament(db: AsyncSession, brand: Brand, name: str, slug: str, **extra) -> Filament:
    filament = Filament(
        brand_id=brand.id, name=name, slug=slug, material_type=extra.pop("material_type", "PETG"),
        **extra,
    )
    db.add(filament)
    await db.flush()
    return filament


def _preset(filament: Filament, name: str, **extra) -> Preset:
    return Preset(
        filament_id=filament.id,
        name=name,
        extruder_temp=240.0,
        bed_temp=80.0,
        moderation_status=extra.pop("moderation_status", PresetModerationStatus.APPROVED),
        active=True,
        **extra,
    )


@pytest.mark.asyncio
async def test_admin_merges_typo_brand_and_keeps_old_addresses(
    admin_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    target = Brand(name="GEEETECH", slug="geeetech", active=True)
    source = Brand(name="GREEETECH", slug="greeetech", active=True)
    db_session.add_all([target, source])
    await db_session.flush()
    target_line = FilamentLine(brand_id=target.id, name="Basic")
    source_line = FilamentLine(brand_id=source.id, name="basic")
    db_session.add_all([target_line, source_line])
    await db_session.flush()
    kept = await _filament(db_session, target, "PETG Basic", "petg-basic", line_id=target_line.id)
    duplicate = await _filament(
        db_session, source, "PETG BASIC", "petg-basic", line_id=source_line.id
    )
    unique = await _filament(
        db_session, source, "TPU", "tpu-grey", material_type="TPU", line_id=source_line.id
    )
    preset = _preset(duplicate, "Community PETG", user_id=auth_user.id)
    db_session.add_all(
        [preset, UserSpool(user_id=auth_user.id, filament_id=duplicate.id, initial_weight_g=1000)]
    )
    await db_session.commit()
    source_id, target_id, kept_id, duplicate_id, unique_id = (
        source.id, target.id, kept.id, duplicate.id, unique.id
    )
    preset_id, target_line_id, source_line_id, user_id = (
        preset.id, target_line.id, source_line.id, auth_user.id
    )

    preview = await admin_client.get(
        f"/api/v1/admin/brands/{source.id}/merge-preview", params={"target_id": target.id}
    )
    assert preview.status_code == 200
    rows = {row["source"]["id"]: row for row in preview.json()["filaments"]}
    assert rows[duplicate.id]["suggested_target_id"] == kept.id
    assert rows[duplicate.id]["needs_pair"] is True
    assert rows[unique.id]["needs_pair"] is False

    merged = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={
            "target_id": target.id,
            "filament_pairs": [
                {"source_filament_id": duplicate.id, "target_filament_id": kept.id}
            ],
        },
    )
    assert merged.status_code == 200, merged.text
    db_session.expire_all()

    assert await db_session.get(Brand, source_id) is None
    assert await db_session.get(Filament, duplicate_id) is None
    assert (await db_session.get(Preset, preset_id)).filament_id == kept_id
    spool = await db_session.scalar(select(UserSpool).where(UserSpool.user_id == user_id))
    assert spool.filament_id == kept_id
    moved = await db_session.get(Filament, unique_id)
    assert (moved.brand_id, moved.slug, moved.line_id) == (target_id, "tpu-grey", target_line_id)
    assert await db_session.get(FilamentLine, source_line_id) is None

    old_brand = await admin_client.get("/api/v1/brands/greeetech")
    assert old_brand.json()["id"] == target_id
    old_duplicate = await admin_client.get("/api/v1/filaments/by-slug/greeetech/petg-basic")
    assert old_duplicate.json()["id"] == kept_id
    old_unique = await admin_client.get("/api/v1/filaments/by-slug/greeetech/tpu-grey")
    assert old_unique.json()["id"] == unique_id


@pytest.mark.asyncio
async def test_brand_merge_refuses_unpaired_address_clash_without_changes(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    target = Brand(name="Bambu Lab", slug="bambu-lab", active=True)
    source = Brand(name="BambuLabs", slug="bambulabs", active=True)
    db_session.add_all([target, source])
    await db_session.flush()
    await _filament(db_session, target, "PLA Matte", "pla-matte", material_type="PLA")
    clash = await _filament(db_session, source, "PLA Matte", "pla-matte", material_type="PLA")
    await db_session.commit()
    source_id, clash_id = source.id, clash.id

    response = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={"target_id": target.id, "filament_pairs": []},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_BRAND_MERGE_FILAMENT_CONFLICT"
    db_session.expire_all()
    assert await db_session.get(Brand, source_id) is not None
    assert (await db_session.get(Filament, clash_id)).brand_id == source_id


@pytest.mark.asyncio
async def test_brand_merge_never_removes_a_manufacturer_brand(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    target = Brand(name="Sunlu", slug="sunlu", active=True)
    source = Brand(name="Sunlu Official", slug="sunlu-official", active=True, verified=True)
    db_session.add_all([target, source])
    await db_session.commit()

    response = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={"target_id": target.id, "filament_pairs": []},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_BRAND_MERGE_SOURCE_REPRESENTED"
    assert await db_session.get(Brand, source.id) is not None


@pytest.mark.asyncio
async def test_brand_merge_combines_complementary_country_details(
    admin_client: AsyncClient, db_session: AsyncSession,
) -> None:
    target = Brand(name="Market Merge Target", slug="market-merge-target", active=True)
    source = Brand(name="Market Merge Source", slug="market-merge-source", active=True)
    db_session.add_all([target, source])
    await db_session.flush()
    db_session.add_all([
        BrandCountryCell(brand_id=target.id, country="TR", website="https://target.example"),
        BrandCountryCell(brand_id=source.id, country="TR", description="Local description", published=True),
    ])
    await db_session.commit()

    response = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={"target_id": target.id, "filament_pairs": []},
    )
    assert response.status_code == 200, response.text
    target_id = target.id
    db_session.expire_all()
    cell = await db_session.scalar(select(BrandCountryCell).where(BrandCountryCell.brand_id == target_id))
    assert (cell.website, cell.description, cell.published) == (
        "https://target.example", "Local description", True,
    )


@pytest.mark.asyncio
async def test_brand_merge_refuses_conflicting_country_details(
    admin_client: AsyncClient, db_session: AsyncSession,
) -> None:
    target = Brand(name="Country Clash Target", slug="country-clash-target", active=True)
    source = Brand(name="Country Clash Source", slug="country-clash-source", active=True)
    db_session.add_all([target, source])
    await db_session.flush()
    db_session.add_all([
        BrandCountryCell(brand_id=target.id, country="TR", website="https://target.example"),
        BrandCountryCell(brand_id=source.id, country="TR", website="https://source.example"),
    ])
    await db_session.commit()

    response = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={"target_id": target.id, "filament_pairs": []},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_CATALOG_MERGE_COUNTRY_CONFLICT"
    source_id = source.id
    db_session.expire_all()
    assert await db_session.get(Brand, source_id) is not None


@pytest.mark.asyncio
async def test_brand_merge_keeps_immutable_monthly_releases(
    admin_client: AsyncClient, db_session: AsyncSession,
) -> None:
    target = Brand(name="Analytics Target", slug="analytics-target", active=True)
    source = Brand(name="Analytics Source", slug="analytics-source", active=True)
    db_session.add_all([target, source])
    await db_session.flush()
    for brand in (target, source):
        db_session.add(BrandMonthlyAnalyticsRelease(
            brand_id=brand.id, month=date(2026, 8, 1),
            captured_at=datetime.now(timezone.utc), spool_count=12,
        ))
    await db_session.commit()

    response = await admin_client.post(
        f"/api/v1/admin/brands/{source.id}/merge",
        json={"target_id": target.id, "filament_pairs": []},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_BRAND_MERGE_ANALYTICS_CONFLICT"
    source_id = source.id
    db_session.expire_all()
    assert await db_session.get(Brand, source_id) is not None


@pytest.mark.asyncio
async def test_filament_merge_combines_market_data_and_rejects_conflicts(
    admin_client: AsyncClient, db_session: AsyncSession,
) -> None:
    brand = Brand(name="Filament Market Merge", slug="filament-market-merge", active=True)
    db_session.add(brand)
    await db_session.flush()
    target = await _filament(db_session, brand, "PETG", "petg-target")
    source = await _filament(db_session, brand, "PETG", "petg-source")
    db_session.add_all([
        FilamentCountryCell(
            filament_id=target.id, country="TR", product_url="https://target.example",
            availability=CountryAvailability.unknown,
        ),
        FilamentCountryCell(
            filament_id=source.id, country="TR", market_note="Local supply",
            availability=CountryAvailability.available, published=True,
        ),
    ])
    await db_session.commit()
    response = await admin_client.post(
        f"/api/v1/filaments/{source.id}/merge", json={"target_id": target.id},
    )
    assert response.status_code == 200, response.text
    target_id, brand_id = target.id, brand.id
    db_session.expire_all()
    cell = await db_session.scalar(select(FilamentCountryCell).where(FilamentCountryCell.filament_id == target_id))
    assert (cell.product_url, cell.market_note, cell.availability, cell.published) == (
        "https://target.example", "Local supply", CountryAvailability.available, True,
    )

    brand = await db_session.get(Brand, brand_id)
    another = await _filament(db_session, brand, "PETG", "petg-conflict")
    db_session.add(FilamentCountryCell(
        filament_id=another.id, country="TR", product_url="https://source.example",
    ))
    await db_session.commit()
    rejected = await admin_client.post(
        f"/api/v1/filaments/{another.id}/merge", json={"target_id": target_id},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "ERR_CATALOG_MERGE_COUNTRY_CONFLICT"
    another_id = another.id
    db_session.expire_all()
    assert await db_session.get(Filament, another_id) is not None


async def _representative_headers(db: AsyncSession, brand: Brand) -> dict[str, str]:
    organization = Organization(name="Merge Org", slug=f"merge-org-{brand.id}")
    db.add(organization)
    await db.flush()
    user = User(
        email=f"merge-rep-{brand.id}@example.com",
        username=f"merge_rep_{brand.id}",
        password_hash=get_password_hash("testpassword123"),
        active=True,
        email_verified=True,
        active_organization_id=organization.id,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.flush()
    db.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=OrganizationMemberRole.OWNER,
                active=True,
                all_brands=True,
            ),
            BrandTerritorialGrant(
                brand_id=brand.id,
                organization_id=organization.id,
                country=None,
                status=GrantStatus.active,
                source=GrantSource.invitation,
                edit_all_filaments_common=True,
            ),
        ]
    )
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


@pytest.mark.asyncio
async def test_representative_merges_filaments_and_presets_stay_separate(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Merge Maker", slug="merge-maker", active=True, verified=True)
    other = Brand(name="Other Maker", slug="other-maker", active=True)
    db_session.add_all([brand, other])
    await db_session.flush()
    kept = await _filament(db_session, brand, "PLA Matte Ivory", "pla-matte-ivory", material_type="PLA")
    duplicate = await _filament(
        db_session, brand, "PLA Matte", "pla-matte", material_type="PLA", qr_code="FHUB-DUP1"
    )
    foreign = await _filament(db_session, other, "PLA Matte", "pla-matte", material_type="PLA")
    kept_weighted = _preset(
        kept, "kept Gen", is_weighted=True,
        moderation_status=PresetModerationStatus.AUTO_GENERATED,
    )
    duplicate_weighted = _preset(
        duplicate, "dup Gen", is_weighted=True,
        moderation_status=PresetModerationStatus.AUTO_GENERATED,
    )
    kept_preset = _preset(kept, "Kept profile", user_id=auth_user.id)
    duplicate_preset = _preset(duplicate, "Duplicate profile", user_id=auth_user.id)
    db_session.add_all([kept_weighted, duplicate_weighted, kept_preset, duplicate_preset])
    await db_session.flush()
    db_session.add_all(
        [
            UserSavedPreset(user_id=auth_user.id, preset_id=duplicate_weighted.id),
            FilamentReview(
                filament_id=duplicate.id, user_id=auth_user.id, preset_id=duplicate_preset.id,
                success=True, rating=5.0, comment="Community profile review",
            ),
            FilamentReview(
                filament_id=duplicate.id, user_id=auth_user.id, preset_id=duplicate_weighted.id,
                success=False, rating=2.0, comment="Duplicate material review",
            ),
            FilamentReview(
                filament_id=kept.id, user_id=auth_user.id, preset_id=kept_weighted.id,
                success=True, rating=4.0, comment="Kept material review",
            ),
        ]
    )
    await db_session.commit()
    kept_id, duplicate_id, foreign_id = kept.id, duplicate.id, foreign.id
    kept_weighted_id, kept_preset_id, duplicate_preset_id = (
        kept_weighted.id, kept_preset.id, duplicate_preset.id
    )
    user_id = auth_user.id
    representative = await _representative_headers(db_session, brand)

    forbidden = await auth_client.post(
        f"/api/v1/filaments/{duplicate_id}/merge", json={"target_id": kept_id}
    )
    assert forbidden.status_code == 403

    candidates = await auth_client.get(
        f"/api/v1/filaments/{duplicate_id}/merge-candidates", headers=representative
    )
    assert candidates.status_code == 200
    assert [item["id"] for item in candidates.json()["candidates"]] == [kept_id]

    cross_brand = await auth_client.post(
        f"/api/v1/filaments/{duplicate_id}/merge",
        json={"target_id": foreign_id},
        headers=representative,
    )
    assert cross_brand.status_code == 409

    merged = await auth_client.post(
        f"/api/v1/filaments/{duplicate_id}/merge",
        json={"target_id": kept_id},
        headers=representative,
    )
    assert merged.status_code == 200, merged.text
    db_session.expire_all()

    assert await db_session.get(Filament, duplicate_id) is None
    presets = (
        await db_session.scalars(select(Preset).where(Preset.filament_id == kept_id))
    ).all()
    assert {preset.id for preset in presets} == {
        kept_weighted_id,
        kept_preset_id,
        duplicate_preset_id,
    }
    saved = await db_session.scalar(
        select(UserSavedPreset).where(UserSavedPreset.user_id == user_id)
    )
    assert saved.preset_id == kept_weighted_id
    reviews = (
        await db_session.scalars(select(FilamentReview).where(FilamentReview.filament_id == kept_id))
    ).all()
    assert {review.comment: (review.rating, review.preset_id) for review in reviews} == {
        "Community profile review": (5.0, duplicate_preset_id),
        "Duplicate material review": (2.0, None),
        "Kept material review": (4.0, kept_weighted_id),
    }
    listed = await auth_client.get(f"/api/v1/filament-reviews/filament/{kept_id}")
    assert listed.status_code == 200
    assert listed.json()["total"] == 3
    assert {item["comment"] for item in listed.json()["items"]} == {
        review.comment for review in reviews
    }
    assert (await db_session.get(Filament, kept_id)).qr_code == "FHUB-DUP1"
    old_address = await auth_client.get("/api/v1/filaments/by-slug/merge-maker/pla-matte")
    assert old_address.json()["id"] == kept_id


@pytest.mark.asyncio
async def test_merge_preserves_legacy_reviews_that_share_a_preset(
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Review Merge Maker", slug="review-merge-maker", active=True)
    db_session.add(brand)
    await db_session.flush()
    kept = await _filament(db_session, brand, "PETG Kept", "petg-kept")
    duplicate = await _filament(db_session, brand, "PETG Duplicate", "petg-duplicate")
    preset = _preset(duplicate, "Shared legacy profile")
    db_session.add(preset)
    await db_session.flush()
    db_session.add_all(
        [
            FilamentReview(
                filament_id=kept.id, user_id=auth_user.id, preset_id=preset.id,
                success=True, rating=4.0, comment="Kept review",
            ),
            FilamentReview(
                filament_id=duplicate.id, user_id=auth_user.id, preset_id=preset.id,
                success=False, rating=2.0, comment="Moved review",
            ),
        ]
    )
    await db_session.commit()
    kept_id, preset_id = kept.id, preset.id

    await merge_filaments(db_session, source=duplicate, target=kept)
    await db_session.commit()
    db_session.expire_all()

    reviews = (
        await db_session.scalars(select(FilamentReview).where(FilamentReview.filament_id == kept_id))
    ).all()
    assert {review.comment: review.preset_id for review in reviews} == {
        "Kept review": preset_id,
        "Moved review": None,
    }


@pytest.mark.asyncio
async def test_brand_creation_points_at_existing_brand_with_typo(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add(Brand(name="Bambu Lab", slug="bambu-lab", active=True))
    await db_session.commit()

    for spelling in ("bambu lab", "BambuLab", "Bambu-Lab ", "Bambu  lab"):
        response = await auth_client.post(
            "/api/v1/brands/", params={"confirm_similar": True}, json={"name": spelling}
        )
        assert response.status_code == 409, spelling
        assert response.json()["detail"]["code"] == "ERR_BRAND_NAME_EXISTS"

    for typo in ("BambuLabs", "Bambu Labb"):
        response = await auth_client.post("/api/v1/brands/", json={"name": typo})
        assert response.status_code == 409, typo
        detail = response.json()["detail"]
        assert detail["code"] == "ERR_BRAND_SIMILAR_EXISTS"
        assert detail["params"]["candidates"][0]["name"] == "Bambu Lab"

    confirmed = await auth_client.post(
        "/api/v1/brands/", params={"confirm_similar": True}, json={"name": "BambuLabs"}
    )
    assert confirmed.status_code == 201


@pytest.mark.asyncio
async def test_admin_sees_typo_brand_pairs(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            Brand(name="GEEETECH", slug="geeetech", active=True),
            Brand(name="GREEETECH", slug="greeetech", active=True),
            Brand(name="U3", slug="u3", active=True),
            Brand(name="U4", slug="u4", active=True),
            Brand(name="SeedBrand 0001", slug="seed-brand-0001", active=True),
            Brand(name="SeedBrand 0002", slug="seed-brand-0002", active=True),
        ]
    )
    await db_session.commit()

    response = await admin_client.get("/api/v1/admin/brands/duplicates")

    assert response.status_code == 200
    pairs = {
        frozenset((pair["first"]["name"], pair["second"]["name"])) for pair in response.json()
    }
    assert pairs == {frozenset(("GEEETECH", "GREEETECH"))}
