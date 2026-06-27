"""Tests for filaments endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament


@pytest.mark.asyncio
async def test_list_filaments_empty(client: AsyncClient):
    """Test listing filaments when database is empty."""
    response = await client.get("/api/v1/filaments/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


@pytest.mark.asyncio
async def test_create_filament(auth_client: AsyncClient, db_session: AsyncSession):
    """Test creating a filament."""
    # Create brand first
    brand = Brand(
        name="Test Brand",
        slug="test-brand",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Create filament
    filament_data = {
        "brand_id": brand.id,
        "name": "Test Filament",
        "material_type": "PLA",
        "color_name": "Red",
        "color_hex": "#FF0000",
        "diameter": 1.75,
        "density": 1.24,
        "price_per_kg": 800.0,
        "spool_weight": 1000.0,
        "description": "Test filament description",
    }
    response = await auth_client.post("/api/v1/filaments/", json=filament_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == filament_data["name"]
    assert data["material_type"] == filament_data["material_type"]
    assert data["id"] is not None
    assert data["availability"] == "available"


@pytest.mark.asyncio
async def test_create_filament_with_availability(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """A brand-set availability status is stored and returned."""
    brand = Brand(name="Avail Brand", slug="avail-brand")
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Discontinued PLA",
            "material_type": "PLA",
            "availability": "discontinued",
        },
    )
    assert response.status_code == 201
    filament_id = response.json()["id"]
    assert response.json()["availability"] == "discontinued"

    patch = await admin_client.patch(
        f"/api/v1/filaments/{filament_id}", json={"availability": "out_of_stock"}
    )
    assert patch.status_code == 200
    assert patch.json()["availability"] == "out_of_stock"


@pytest.mark.asyncio
async def test_get_filament(client: AsyncClient, db_session: AsyncSession):
    """Test getting a filament by ID."""
    # Create brand and filament
    brand = Brand(
        name="Test Brand 2",
        slug="test-brand-2",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament 2",
        slug="test-filament-2",
        material_type="PETG",
        color_name="Blue",
        color_hex="#0000FF",
        diameter=1.75,
        density=1.27,
        price_per_kg=950.0,
        spool_weight=1000.0,
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Get filament via API
    response = await client.get(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == filament.id
    assert data["name"] == filament.name
    assert data["material_type"] == filament.material_type


@pytest.mark.asyncio
async def test_get_filament_not_found(client: AsyncClient):
    """Test getting non-existent filament."""
    response = await client.get("/api/v1/filaments/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_filaments_filter_by_brand(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering filaments by brand."""
    # Create brands
    brand1 = Brand(name="Brand 1", slug="brand-1", active=True)
    brand2 = Brand(name="Brand 2", slug="brand-2", active=True)
    db_session.add_all([brand1, brand2])
    await db_session.commit()
    await db_session.refresh(brand1)
    await db_session.refresh(brand2)
    
    # Create filaments
    filament1 = Filament(
        brand_id=brand1.id,
        name="Filament 1",
        slug="filament-1",
        material_type="PLA",
        active=True,
    )
    filament2 = Filament(
        brand_id=brand2.id,
        name="Filament 2",
        slug="filament-2",
        material_type="PETG",
        active=True,
    )
    db_session.add_all([filament1, filament2])
    await db_session.commit()
    
    # Filter by brand1
    response = await client.get(f"/api/v1/filaments/?brand_id={brand1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == filament1.id


@pytest.mark.asyncio
async def test_list_filaments_filter_by_material_type(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering filaments by material type."""
    # Create brand
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Create filaments with different types
    filament1 = Filament(
        brand_id=brand.id,
        name="PLA Filament",
        slug="pla-filament",
        material_type="PLA",
        active=True,
    )
    filament2 = Filament(
        brand_id=brand.id,
        name="PETG Filament",
        slug="petg-filament",
        material_type="PETG",
        active=True,
    )
    db_session.add_all([filament1, filament2])
    await db_session.commit()
    
    # Filter by PLA
    response = await client.get("/api/v1/filaments/?material_type=PLA")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["material_type"] == "PLA"


@pytest.mark.asyncio
async def test_get_filament_presets(client: AsyncClient, db_session: AsyncSession):
    """Test getting presets for a filament."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Get presets
    response = await client.get(f"/api/v1/filaments/{filament.id}/presets")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_update_filament(admin_client: AsyncClient, db_session: AsyncSession):
    """Test updating a filament."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Original Name",
        slug="original-name",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Update filament (using PATCH for partial update)
    update_data = {
        "name": "Updated Name",
        "description": "Updated description",
    }
    response = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}", json=update_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]

