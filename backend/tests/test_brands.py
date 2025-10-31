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
async def test_create_brand(client: AsyncClient):
    """Test creating a brand."""
    brand_data = {
        "name": "Test Brand",
        "slug": "test-brand",
        "description": "Test description",
        "website": "https://test.com",
        "verified": False,
    }
    response = await client.post("/api/v1/brands/", json=brand_data)
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

