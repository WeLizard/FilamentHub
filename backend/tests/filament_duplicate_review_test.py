"""Probable-duplicate moderation queue for catalog filaments."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_duplicate_review import FilamentDuplicateReview
from app.models.user import User


async def _brand(db: AsyncSession) -> Brand:
    brand = Brand(name="Bambu Lab", slug="bambu-lab", verified=False, active=True)
    db.add(brand)
    await db.flush()
    return brand


async def _filament(
    db: AsyncSession,
    brand: Brand,
    name: str,
    color_name: str | None,
    color_hex: str | None,
    slug: str,
    created_by: int | None = None,
) -> Filament:
    filament = Filament(
        brand_id=brand.id,
        name=name,
        slug=slug,
        material_type="PLA",
        color_name=color_name,
        color_hex=color_hex,
        diameter=1.75,
        created_by_user_id=created_by,
    )
    db.add(filament)
    await db.flush()
    return filament


async def _review_count(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(FilamentDuplicateReview)) or 0)


def _payload(brand: Brand, name: str, color: str, hex_: str) -> dict:
    return {
        "brand_id": brand.id,
        "name": name,
        "material_type": "PLA",
        "color_name": color,
        "color_hex": hex_,
        "diameter": 1.75,
    }


@pytest.mark.asyncio
async def test_creating_a_probable_duplicate_succeeds_and_queues_one_review(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    brand = await _brand(db_session)
    older = await _filament(db_session, brand, "PLA Matte Grey", "Grey", "#A6A6A6", "pla-matte-grey")
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/filaments/", json=_payload(brand, "PLA Matte", "Grey", "#A6A6A6")
    )

    assert response.status_code == 201
    reviews = (await db_session.scalars(select(FilamentDuplicateReview))).all()
    assert len(reviews) == 1
    assert reviews[0].origin == "creation"
    assert reviews[0].status == "pending"
    assert reviews[0].filament_id == response.json()["id"]
    assert reviews[0].candidate_id == older.id
    created = await db_session.get(Filament, response.json()["id"])
    assert created.created_by_user_id == auth_user.id


@pytest.mark.asyncio
async def test_creating_a_different_product_queues_nothing(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    await _filament(db_session, brand, "PLA Matte Grey", "Grey", "#A6A6A6", "pla-matte-grey")
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/filaments/", json=_payload(brand, "PLA Silk", "Grey", "#A6A6A6")
    )

    assert response.status_code == 201
    assert await _review_count(db_session) == 0


@pytest.mark.asyncio
async def test_exact_duplicate_is_still_rejected_without_a_review(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    await _filament(db_session, brand, "PLA Matte", "White", "#FFFFFF", "pla-matte-white")
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/filaments/", json=_payload(brand, "pla-matte", "white", "#FFFFFF")
    )

    assert response.status_code == 409
    assert await _review_count(db_session) == 0


@pytest.mark.asyncio
async def test_admin_lists_pairs_with_summaries_and_author(
    admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
) -> None:
    brand = await _brand(db_session)
    older = await _filament(db_session, brand, "PLA Matte", None, "#68724D", "pla-matte")
    newer = await _filament(
        db_session, brand, "Matte", "Dark Green", "#68724D", "matte", created_by=admin_user.id
    )
    db_session.add(
        FilamentDuplicateReview(filament_id=newer.id, candidate_id=older.id, origin="creation")
    )
    await db_session.commit()

    listing = await admin_client.get("/api/v1/admin/filaments/duplicates")
    count = await admin_client.get("/api/v1/admin/filaments/duplicates/count")

    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["brand_name"] == "Bambu Lab"
    assert item["created_by"] == {"id": admin_user.id, "username": admin_user.username}
    assert item["filament"]["id"] == newer.id
    assert item["candidate"]["id"] == older.id
    assert count.json() == {"pending_count": 1}


@pytest.mark.asyncio
async def test_regular_user_cannot_use_the_queue(auth_client: AsyncClient) -> None:
    for method, path in (
        ("get", "/api/v1/admin/filaments/duplicates"),
        ("get", "/api/v1/admin/filaments/duplicates/count"),
        ("post", "/api/v1/admin/filaments/duplicates/scan"),
        ("post", "/api/v1/admin/filaments/duplicates/1/dismiss"),
    ):
        assert (await getattr(auth_client, method)(path)).status_code == 403


@pytest.mark.asyncio
async def test_dismissed_pair_leaves_the_queue_and_a_scan_does_not_bring_it_back(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    older = await _filament(db_session, brand, "PLA Matte", None, "#68724D", "pla-matte")
    newer = await _filament(db_session, brand, "Matte", "Dark Green", "#68724D", "matte")
    review = FilamentDuplicateReview(filament_id=newer.id, candidate_id=older.id, origin="creation")
    db_session.add(review)
    await db_session.commit()

    dismissed = await admin_client.post(f"/api/v1/admin/filaments/duplicates/{review.id}/dismiss")
    again = await admin_client.post(f"/api/v1/admin/filaments/duplicates/{review.id}/dismiss")
    missing = await admin_client.post("/api/v1/admin/filaments/duplicates/999999/dismiss")
    scan = await admin_client.post("/api/v1/admin/filaments/duplicates/scan")

    assert dismissed.status_code == 204
    # A second admin clicking the same row must not see an error.
    assert again.status_code == 204
    assert missing.status_code == 204
    assert scan.json() == {"added": 0}
    assert (await admin_client.get("/api/v1/admin/filaments/duplicates")).json()["total"] == 0
    count = await admin_client.get("/api/v1/admin/filaments/duplicates/count")
    assert count.json() == {"pending_count": 0}


@pytest.mark.asyncio
async def test_scan_finds_an_existing_pair_once(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    older = await _filament(db_session, brand, "Matte", "Dark Green", "#68724D", "matte")
    newer = await _filament(db_session, brand, "PLA Matte", None, "#68724D", "pla-matte")
    await _filament(db_session, brand, "PLA Silk", "Dark Green", "#68724D", "pla-silk")
    await db_session.commit()

    first = await admin_client.post("/api/v1/admin/filaments/duplicates/scan")
    second = await admin_client.post("/api/v1/admin/filaments/duplicates/scan")

    assert first.json() == {"added": 1}
    assert second.json() == {"added": 0}
    review = (await db_session.scalars(select(FilamentDuplicateReview))).one()
    assert (review.filament_id, review.candidate_id, review.origin) == (newer.id, older.id, "scan")


@pytest.mark.asyncio
async def test_merging_the_source_removes_its_review_rows(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    kept = await _filament(db_session, brand, "PLA Matte", "Grey", "#A6A6A6", "pla-matte")
    source = await _filament(db_session, brand, "PLA Matte Grey", "Grey", "#A6A6A6", "pla-matte-grey")
    db_session.add(
        FilamentDuplicateReview(filament_id=source.id, candidate_id=kept.id, origin="scan")
    )
    await db_session.commit()

    merged = await admin_client.post(
        f"/api/v1/filaments/{source.id}/merge", json={"target_id": kept.id}
    )

    assert merged.status_code == 200, merged.text
    assert await _review_count(db_session) == 0


@pytest.mark.asyncio
async def test_failure_in_the_hook_does_not_fail_creation(
    auth_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand = await _brand(db_session)
    await _filament(db_session, brand, "PLA Matte Grey", "Grey", "#A6A6A6", "pla-matte-grey")
    await db_session.commit()

    def broken(*args, **kwargs):
        raise RuntimeError("identity failed")

    monkeypatch.setattr("app.services.filament_duplicate_service.identity_of", broken)

    response = await auth_client.post(
        "/api/v1/filaments/", json=_payload(brand, "PLA Matte", "Grey", "#A6A6A6")
    )

    assert response.status_code == 201
    assert response.json()["name"] == "PLA Matte"
    assert await _review_count(db_session) == 0


@pytest.mark.asyncio
async def test_scan_groups_by_material_type_and_never_duplicates_a_pair(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    brand = await _brand(db_session)
    await _filament(db_session, brand, "Matte", "Grey", "#A6A6A6", "matte")
    await _filament(db_session, brand, "Matte", "Grey", "#A6A6A6", "matte-2")
    other = await _filament(db_session, brand, "Matte", "Grey", "#A6A6A6", "matte-petg")
    other.material_type = " petg "
    await db_session.commit()

    first = await admin_client.post("/api/v1/admin/filaments/duplicates/scan")
    second = await admin_client.post("/api/v1/admin/filaments/duplicates/scan")

    # The PETG record shares name and colour but is a different kind: no pair.
    assert first.json() == {"added": 1}
    assert second.json() == {"added": 0}


@pytest.mark.asyncio
async def test_concurrent_insert_of_an_existing_pair_is_skipped(
    db_session: AsyncSession,
) -> None:
    from app.services.filament_duplicate_service import _insert_pair

    brand = await _brand(db_session)
    older = await _filament(db_session, brand, "Matte", "Grey", "#A6A6A6", "matte")
    newer = await _filament(db_session, brand, "Matte", "Grey", "#A6A6A6", "matte-2")
    await db_session.commit()

    assert await _insert_pair(db_session, newer.id, older.id, "creation") == 1
    assert await _insert_pair(db_session, newer.id, older.id, "scan") == 0
    assert await _review_count(db_session) == 1


@pytest.mark.asyncio
async def test_merge_candidates_include_returns_the_pair_beyond_the_pool_limit(
    admin_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand = await _brand(db_session)
    source = await _filament(db_session, brand, "Matte", "Dark Green", "#68724D", "matte")
    await _filament(db_session, brand, "Aaa Other", "Red", "#FF0000", "aaa")
    candidate = await _filament(db_session, brand, "PLA Matte", None, "#68724D", "pla-matte")
    await db_session.commit()
    monkeypatch.setattr("app.api.v1.endpoints.filaments.MERGE_CANDIDATE_POOL_LIMIT", 1)
    url = f"/api/v1/filaments/{source.id}/merge-candidates"

    plain = (await admin_client.get(url)).json()["candidates"]
    included = (await admin_client.get(url, params={"include": candidate.id})).json()["candidates"]

    assert candidate.id not in [item["id"] for item in plain]
    assert included[0]["id"] == candidate.id
    assert included[0]["likely_same"] is True
    assert [item["id"] for item in included].count(candidate.id) == 1
