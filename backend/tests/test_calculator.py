"""Tests for calculator endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_calculator_estimate_basic(client: AsyncClient):
    """Test basic cost estimation by weight without electricity."""
    request_data = {
        "pricing_method": "by_weight",
        "weight_g": 100.0,
        "spool_price": 800.0,
        "spool_weight_kg": 1.0,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "cost_material" in data
    assert "cost_total" in data
    assert "weight_kg" in data
    # Material: (800 / 1.0) / 1000 * 100 = 80 rubles
    assert data["cost_material"] == 80.0
    assert data["cost_total"] == 80.0
    assert data["cost_electricity"] == 0.0
    assert data["weight_kg"] == 0.1


@pytest.mark.asyncio
async def test_calculator_estimate_with_electricity(client: AsyncClient):
    """Test cost estimation with electricity cost."""
    request_data = {
        "pricing_method": "by_weight",
        "weight_g": 200.0,
        "spool_price": 800.0,
        "spool_weight_kg": 1.0,
        "time_sec": 3600.0,  # 1 hour
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
    # Material: (800 / 1.0) / 1000 * 200 = 160 rubles
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
    """Test by_weight estimation fails (400) when weight is missing."""
    request_data = {
        "pricing_method": "by_weight",
        "spool_price": 800.0,
        "spool_weight_kg": 1.0,
    }
    response = await client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 400  # Runtime validation: weight required

