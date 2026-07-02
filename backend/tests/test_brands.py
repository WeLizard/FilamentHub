"""Tests for brands endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand


@pytest.mark.asyncio
async def test_list_brands_empty(client: AsyncClient):
    """Test listing brands when database is empty."""
    response = await client.get("/api/v1/brands/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


@pytest.mark.asyncio
async def test_create_brand(auth_client: AsyncClient):
    """Test creating a brand."""
    brand_data = {
        "name": "Test Brand",
        "slug": "test-brand",
        "description": "Test description",
        "website": "https://test.com",
        "verified": False,
    }
    response = await auth_client.post("/api/v1/brands/", json=brand_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == brand_data["name"]
    assert data["slug"] == brand_data["slug"]
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_get_brand(client: AsyncClient, db_session: AsyncSession):
    """Test getting a brand by ID."""
    # Create brand directly in DB
    brand = Brand(
        name="Test Brand 2",
        slug="test-brand-2",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Get brand via API
    response = await client.get(f"/api/v1/brands/{brand.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == brand.id
    assert data["name"] == brand.name


@pytest.mark.asyncio
async def test_get_brand_not_found(client: AsyncClient):
    """Test getting non-existent brand."""
    response = await client.get("/api/v1/brands/99999")
    assert response.status_code == 404



@pytest.mark.asyncio
async def test_brand_request_proof_files_are_gated(client: AsyncClient, db_session: AsyncSession):
    """Proof documents are not public via /uploads and are served only to owner/admin."""
    import json

    from sqlalchemy import select

    from app.models.brand_request import BrandRequest, BrandRequestType
    from app.models.user import User
    from app.services.file_service import get_upload_root_dir

    async def register(suffix: str) -> dict[str, str]:
        email = f"{suffix}@example.com"
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "username": f"user_{suffix}",
                "password": "testpassword123",
                "role": "user",
            },
        )
        assert resp.status_code == 201
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "testpassword123"},
        )
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    owner_headers = await register("proof-owner")
    other_headers = await register("proof-other")

    owner = (
        await db_session.execute(
            select(User).where(User.email == "proof-owner@example.com")
        )
    ).scalar_one()

    request = BrandRequest(
        user_id=owner.id,
        request_type=BrandRequestType.CREATE,
        new_brand_name="ProofCo",
        proof_files=json.dumps(["brand_requests/0/proof-test.png"]),
    )
    db_session.add(request)
    await db_session.commit()
    await db_session.refresh(request)

    proof_dir = get_upload_root_dir() / "brand_requests" / str(request.id)
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_file = proof_dir / "proof-test.png"
    proof_file.write_bytes(b"proof-bytes")

    try:
        # Public static mount must not serve proof documents
        public = await client.get(
            f"/uploads/brand_requests/{request.id}/proof-test.png"
        )
        assert public.status_code == 404

        endpoint = f"/api/v1/brand-requests/{request.id}/proof/proof-test.png"

        anon = await client.get(endpoint)
        assert anon.status_code == 401

        other = await client.get(endpoint, headers=other_headers)
        assert other.status_code == 403

        ok = await client.get(endpoint, headers=owner_headers)
        assert ok.status_code == 200
        assert ok.content == b"proof-bytes"

        traversal = await client.get(
            f"/api/v1/brand-requests/{request.id}/proof/..%2F..%2Fsecret.png",
            headers=owner_headers,
        )
        assert traversal.status_code == 404
    finally:
        proof_file.unlink(missing_ok=True)
