"""Tests for calculator endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_calculator_estimate_basic(client: AsyncClient):
    """Test basic cost estimation without electricity."""
    request_data = {
        "weight_g": 100.0,
        "time_sec": 3600.0,  # 1 hour (required field)
        "price_per_kg": 800.0,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "cost_material" in data
    assert "cost_total" in data
    assert "weight_kg" in data
    assert "time_hours" in data
    # Cost should be (100g / 1000) * 800 = 80 rubles
    assert data["cost_material"] == 80.0
    assert data["cost_total"] == 80.0
    assert data["cost_electricity"] is None


@pytest.mark.asyncio
async def test_calculator_estimate_with_electricity(client: AsyncClient):
    """Test cost estimation with electricity cost."""
    request_data = {
        "weight_g": 200.0,
        "time_sec": 3600.0,  # 1 hour
        "price_per_kg": 800.0,
        "printer_power_w": 200.0,
        "electricity_cost_per_kwh": 5.5,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "cost_material" in data
    assert "cost_electricity" in data
    assert "cost_total" in data
    # Material: (200g / 1000) * 800 = 160 rubles
    # Electricity: (1 hour) * (0.2 kW) * 5.5 = 1.1 rubles
    assert data["cost_material"] == 160.0
    assert data["cost_electricity"] == pytest.approx(1.1, rel=0.01)
    assert data["cost_total"] == pytest.approx(161.1, rel=0.01)


@pytest.mark.asyncio
async def test_calculator_estimate_validation(client: AsyncClient):
    """Test calculator input validation."""
    # Test with negative weight
    request_data = {
        "weight_g": -100.0,
        "price_per_kg": 800.0,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_calculator_estimate_missing_required(client: AsyncClient):
    """Test calculator with missing required fields."""
    request_data = {
        "price_per_kg": 800.0,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 422  # Validation error

