"""Tests for filament reviews endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User


async def _register_and_login(client: AsyncClient, suffix: str) -> tuple[dict, int]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    reg = await client.post("/api/v1/auth/register", json={
        "email": email, "username": f"user_{suffix}",
        "password": password, "role": "user",
    })
    assert reg.status_code == 201
    user_id = reg.json()["id"]
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id


async def _create_filament(db: AsyncSession) -> Filament:
    brand = Brand(name="Review Brand", slug="review-brand", active=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    filament = Filament(
        brand_id=brand.id, name="Review Filament",
        slug="review-filament", material_type="PLA", active=True,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


async def _create_official_preset(db: AsyncSession, filament_id: int, user_id: int) -> Preset:
    preset = Preset(
        filament_id=filament_id,
        user_id=user_id,
        name="Official Preset",
        is_official=True,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        extruder_temp=200.0,
        bed_temp=60.0,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


@pytest.mark.asyncio
async def test_create_review_without_preset(client: AsyncClient, db_session: AsyncSession):
    """Create a general review (no specific preset)."""
    headers, _ = await _register_and_login(client, "rev-create")
    filament = await _create_filament(db_session)

    response = await client.post("/api/v1/filament-reviews/", headers=headers, json={
        "filament_id": filament.id,
        "success": True,
        "rating": 5,
        "comment": "Great filament",
        "printer_model": "Voron 2.4",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["rating"] == 5
    assert data["filament_id"] == filament.id
    assert data["preset_id"] is None


@pytest.mark.asyncio
async def test_create_review_duplicate_rejected(client: AsyncClient, db_session: AsyncSession):
    """Second review for the same filament+preset is rejected."""
    headers, _ = await _register_and_login(client, "rev-dup")
    filament = await _create_filament(db_session)

    payload = {"filament_id": filament.id, "success": True, "rating": 4}
    r1 = await client.post("/api/v1/filament-reviews/", headers=headers, json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/filament-reviews/", headers=headers, json=payload)
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "ERR_REVIEW_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_list_reviews_for_filament(client: AsyncClient, db_session: AsyncSession):
    """Reviews are returned for the correct filament."""
    headers, _ = await _register_and_login(client, "rev-list")
    filament = await _create_filament(db_session)

    await client.post("/api/v1/filament-reviews/", headers=headers, json={
        "filament_id": filament.id, "success": True, "rating": 3,
    })

    response = await client.get(f"/api/v1/filament-reviews/filament/{filament.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["filament_id"] == filament.id


@pytest.mark.asyncio
async def test_get_rating_stats_empty(client: AsyncClient, db_session: AsyncSession):
    """Stats for filament with no reviews returns zeros."""
    filament = await _create_filament(db_session)

    response = await client.get(f"/api/v1/filament-reviews/filament/{filament.id}/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 0
    assert data["avg_rating"] is None


@pytest.mark.asyncio
async def test_get_rating_stats_with_reviews(client: AsyncClient, db_session: AsyncSession):
    """Stats reflect actual review data."""
    h1, _ = await _register_and_login(client, "rev-stats-a")
    h2, _ = await _register_and_login(client, "rev-stats-b")
    filament = await _create_filament(db_session)

    await client.post("/api/v1/filament-reviews/", headers=h1, json={
        "filament_id": filament.id, "success": True, "rating": 4,
    })
    await client.post("/api/v1/filament-reviews/", headers=h2, json={
        "filament_id": filament.id, "success": False, "rating": 2,
    })

    response = await client.get(f"/api/v1/filament-reviews/filament/{filament.id}/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 2
    assert data["avg_rating"] == 3.0


@pytest.mark.asyncio
async def test_update_own_review(client: AsyncClient, db_session: AsyncSession):
    """Author can update their own review."""
    headers, _ = await _register_and_login(client, "rev-update")
    filament = await _create_filament(db_session)

    create_resp = await client.post("/api/v1/filament-reviews/", headers=headers, json={
        "filament_id": filament.id, "success": True, "rating": 3,
    })
    review_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/filament-reviews/{review_id}", headers=headers,
        json={"rating": 5, "comment": "Changed my mind"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["rating"] == 5


@pytest.mark.asyncio
async def test_update_other_user_review_forbidden(client: AsyncClient, db_session: AsyncSession):
    """Non-author cannot update someone else's review."""
    h_author, _ = await _register_and_login(client, "rev-own")
    h_other, _ = await _register_and_login(client, "rev-other")
    filament = await _create_filament(db_session)

    create_resp = await client.post("/api/v1/filament-reviews/", headers=h_author, json={
        "filament_id": filament.id, "success": True, "rating": 3,
    })
    review_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/api/v1/filament-reviews/{review_id}", headers=h_other,
        json={"rating": 1},
    )
    assert patch_resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_review_deactivates(client: AsyncClient, db_session: AsyncSession):
    """Deleting a review deactivates it (not hard delete)."""
    headers, _ = await _register_and_login(client, "rev-del")
    filament = await _create_filament(db_session)

    create_resp = await client.post("/api/v1/filament-reviews/", headers=headers, json={
        "filament_id": filament.id, "success": True, "rating": 4,
    })
    review_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/filament-reviews/{review_id}", headers=headers)
    assert del_resp.status_code == 204

    # Active-only list should be empty
    list_resp = await client.get(f"/api/v1/filament-reviews/filament/{filament.id}")
    assert list_resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_review_not_found(client: AsyncClient):
    """404 for non-existent review."""
    response = await client.get("/api/v1/filament-reviews/99999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_REVIEW_NOT_FOUND"


@pytest.mark.asyncio
async def test_filament_not_found(client: AsyncClient):
    """404 when listing reviews for non-existent filament."""
    response = await client.get("/api/v1/filament-reviews/filament/99999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_NOT_FOUND"
