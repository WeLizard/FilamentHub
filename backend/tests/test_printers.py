"""Tests for printers endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer import Printer


@pytest.mark.asyncio
async def test_list_printers_empty(client: AsyncClient):
    """Test listing printers when database is empty."""
    response = await client.get("/api/v1/printers/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_get_printer(client: AsyncClient, db_session: AsyncSession):
    """Test getting a printer by ID."""
    # Create printer directly in DB
    printer = Printer(
        name="Ender 3 Pro",
        manufacturer="Creality",
        model="Ender 3 Pro",
        slug="creality-ender-3-pro",
        active=True,
    )
    db_session.add(printer)
    await db_session.commit()
    await db_session.refresh(printer)
    
    # Get printer via API
    response = await client.get(f"/api/v1/printers/{printer.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == printer.id
    assert data["manufacturer"] == printer.manufacturer
    assert data["model"] == printer.model


@pytest.mark.asyncio
async def test_get_printer_not_found(client: AsyncClient):
    """Test getting non-existent printer."""
    response = await client.get("/api/v1/printers/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_printers_filter_by_manufacturer(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering printers by manufacturer."""
    # Create printers
    printer1 = Printer(
        name="Ender 3",
        manufacturer="Creality",
        model="Ender 3",
        slug="creality-ender-3",
        active=True,
    )
    printer2 = Printer(
        name="MK3S+",
        manufacturer="Prusa",
        model="MK3S+",
        slug="prusa-mk3s-plus",
        active=True,
    )
    db_session.add_all([printer1, printer2])
    await db_session.commit()
    
    # Filter by manufacturer
    response = await client.get("/api/v1/printers/?manufacturer=Creality")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["manufacturer"] == "Creality"


@pytest.mark.asyncio
async def test_list_printers_search(client: AsyncClient, db_session: AsyncSession):
    """Test searching printers by model."""
    # Create printers
    printer1 = Printer(
        name="Ender 3 Pro",
        manufacturer="Creality",
        model="Ender 3 Pro",
        slug="creality-ender-3-pro",
        active=True,
    )
    printer2 = Printer(
        name="MK3S+",
        manufacturer="Prusa",
        model="MK3S+",
        slug="prusa-mk3s-plus",
        active=True,
    )
    db_session.add_all([printer1, printer2])
    await db_session.commit()
    
    # Search
    response = await client.get("/api/v1/printers/?search=Ender")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "Ender" in data["items"][0]["model"]

