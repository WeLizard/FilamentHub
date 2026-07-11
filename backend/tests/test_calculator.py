"""Tests for calculator endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_calculator_estimate_basic(admin_client: AsyncClient):
    """Test basic cost estimation by weight without electricity."""
    request_data = {
        "pricing_method": "by_weight",
        "weight_g": 100.0,
        "spool_price": 800.0,
        "spool_weight_kg": 1.0,
    }
    response = await admin_client.post(
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
async def test_calculator_estimate_with_electricity(admin_client: AsyncClient):
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
    response = await admin_client.post(
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
async def test_calculator_estimate_uses_independent_multi_material_lines(
    admin_client: AsyncClient,
):
    """Each tool/material line keeps its own price and contributes to the total."""
    request_data = {
        "pricing_method": "by_weight",
        "quantity": 2,
        "material_lines": [
            {
                "line_id": "job-1:t0",
                "job_key": "job-1",
                "tool_index": 0,
                "label": "PLA model",
                "weight_g": 100,
                "spool_price": 800,
                "spool_weight_kg": 1,
                "price_source": "spool",
                "spool_id": 10,
                "filament_id": 20,
            },
            {
                "line_id": "job-1:t1",
                "job_key": "job-1",
                "tool_index": 1,
                "label": "Support material",
                "weight_g": 50,
                "spool_price": 2000,
                "spool_weight_kg": 1,
                "price_source": "filamenthub",
                "filament_id": 21,
            },
        ],
    }

    response = await admin_client.post("/api/v1/calculator/estimate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["cost_material"] == 360.0
    assert data["cost_total"] == 360.0
    assert data["weight_kg"] == 0.3
    assert data["material_line_costs"] == [
        {
            "line_id": "job-1:t0",
            "job_key": "job-1",
            "tool_index": 0,
            "label": "PLA model",
            "weight_g": 200.0,
            "price_per_gram": 0.8,
            "cost": 160.0,
            "price_source": "spool",
            "spool_id": 10,
            "filament_id": 20,
        },
        {
            "line_id": "job-1:t1",
            "job_key": "job-1",
            "tool_index": 1,
            "label": "Support material",
            "weight_g": 100.0,
            "price_per_gram": 2.0,
            "cost": 200.0,
            "price_source": "filamenthub",
            "spool_id": None,
            "filament_id": 21,
        },
    ]


@pytest.mark.asyncio
async def test_calculator_estimate_multiplies_each_print_job_independently(
    admin_client: AsyncClient,
):
    """Different plates keep their own repeat count, time, material, and bed preparation."""
    request_data = {
        "pricing_method": "combined",
        "quantity": 1,
        "printing_rate_per_hour": 100,
        "bed_prep_cost_per_print": 10,
        "overhead_percent": 0,
        "markup_percent": 0,
        "print_jobs": [
            {
                "job_key": "plate-a",
                "repeats": 2,
                "output_quantity_per_run": 200,
                "print_time_seconds": 3600,
            },
            {
                "job_key": "plate-b",
                "repeats": 3,
                "output_quantity_per_run": 1,
                "print_time_seconds": 1800,
            },
        ],
        "material_lines": [
            {
                "line_id": "plate-a:t0",
                "job_key": "plate-a",
                "tool_index": 0,
                "weight_g": 100,
                "spool_price": 1000,
                "spool_weight_kg": 1,
                "price_source": "manual",
            },
            {
                "line_id": "plate-b:t0",
                "job_key": "plate-b",
                "tool_index": 0,
                "weight_g": 50,
                "spool_price": 2000,
                "spool_weight_kg": 1,
                "price_source": "manual",
            },
        ],
    }

    response = await admin_client.post("/api/v1/calculator/estimate", json=request_data)

    assert response.status_code == 200
    data = response.json()
    assert data["quantity"] == 403
    assert data["print_runs"] == 5
    assert data["weight_kg"] == 0.35
    assert data["time_hours"] == 0.7
    assert data["total_time_hours"] == 3.5
    assert data["cost_material"] == 500.0
    assert data["cost_bed_prep"] == 50.0
    assert data["cost_printing"] == 350.0
    assert [line["weight_g"] for line in data["material_line_costs"]] == [200.0, 150.0]


@pytest.mark.asyncio
async def test_calculator_estimate_rejects_material_line_for_unknown_print_job(
    admin_client: AsyncClient,
):
    response = await admin_client.post(
        "/api/v1/calculator/estimate",
        json={
            "pricing_method": "by_weight",
            "print_jobs": [
                {
                    "job_key": "plate-a",
                    "repeats": 1,
                    "output_quantity_per_run": 1,
                    "print_time_seconds": 60,
                }
            ],
            "material_lines": [
                {
                    "line_id": "plate-b:t0",
                    "job_key": "plate-b",
                    "weight_g": 10,
                    "spool_price": 1000,
                    "spool_weight_kg": 1,
                    "price_source": "manual",
                }
            ],
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_calculator_history_preserves_all_batch_jobs(admin_client: AsyncClient):
    """A batch history round-trip keeps every uploaded file/plate and material line."""
    estimate_request = {
        "pricing_method": "by_weight",
        "material_lines": [
            {
                "line_id": "upload-0:plate-1:t0",
                "job_key": "upload-0:plate-1",
                "tool_index": 0,
                "weight_g": 10,
                "spool_price": 1000,
                "spool_weight_kg": 1,
                "price_source": "manual",
            },
            {
                "line_id": "upload-1:t0",
                "job_key": "upload-1",
                "tool_index": 0,
                "weight_g": 20,
                "spool_price": 800,
                "spool_weight_kg": 1,
                "price_source": "spool",
            },
        ],
    }
    estimate_response = await admin_client.post(
        "/api/v1/calculator/estimate",
        json=estimate_request,
    )
    assert estimate_response.status_code == 200

    parsed_jobs = [
        {
            "job_key": "upload-0:plate-1",
            "parsed_gcode": {
                "file_name": "project.gcode.3mf",
                "file_size_bytes": 1024,
                "plate_index": 1,
                "available_plate_indices": [1, 2],
                "container_format": "gcode_3mf",
                "thumbnail_data_url": "data:image/png;base64,AAAA",
                "materials": [],
            },
        },
        {
            "job_key": "upload-1",
            "parsed_gcode": {
                "file_name": "standalone.gcode",
                "file_size_bytes": 2048,
                "container_format": "plain_gcode",
                "materials": [],
            },
        },
    ]
    history_response = await admin_client.post(
        "/api/v1/calculator/history",
        json={
            "request_data": estimate_request,
            "result_data": estimate_response.json(),
            "parsed_jobs": parsed_jobs,
        },
    )

    assert history_response.status_code == 201
    saved = history_response.json()
    assert saved["title"] == "project.gcode.3mf"
    assert saved["parsed_gcode"]["file_name"] == "project.gcode.3mf"
    assert [job["job_key"] for job in saved["parsed_jobs"]] == [
        "upload-0:plate-1",
        "upload-1",
    ]
    assert all(
        job["parsed_gcode"]["thumbnail_data_url"] is None
        for job in saved["parsed_jobs"]
    )


@pytest.mark.asyncio
async def test_calculator_estimate_validation(admin_client: AsyncClient):
    """Test calculator input validation."""
    # Test with negative weight
    request_data = {
        "weight_g": -100.0,
        "price_per_kg": 800.0,
    }
    response = await admin_client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_calculator_estimate_missing_required(admin_client: AsyncClient):
    """Test by_weight estimation fails (400) when weight is missing."""
    request_data = {
        "pricing_method": "by_weight",
        "spool_price": 800.0,
        "spool_weight_kg": 1.0,
    }
    response = await admin_client.post(
        "/api/v1/calculator/estimate", json=request_data
    )
    assert response.status_code == 400  # Runtime validation: weight required


_ACCESS_REQUEST = {
    "pricing_method": "by_weight",
    "weight_g": 100.0,
    "spool_price": 800.0,
    "spool_weight_kg": 1.0,
}


@pytest.mark.asyncio
async def test_calculator_estimate_anonymous_401(client: AsyncClient):
    """Calculator requires auth: anonymous request → 401."""
    response = await client.post("/api/v1/calculator/estimate", json=_ACCESS_REQUEST)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_calculator_estimate_forbidden_when_paywall_enforced(auth_client: AsyncClient, db_session):
    """Paywall enforced + no valid subscription → 403."""
    from app.services.subscription_service import set_paywall_enforced

    await set_paywall_enforced(db_session, True)
    try:
        response = await auth_client.post("/api/v1/calculator/estimate", json=_ACCESS_REQUEST)
        assert response.status_code == 403
    finally:
        await set_paywall_enforced(db_session, False)


@pytest.mark.asyncio
async def test_calculator_estimate_open_when_paywall_off(auth_client: AsyncClient, db_session):
    """Reverse trial: with the paywall off (default launch state) any authenticated user has access."""
    from app.services.subscription_service import set_paywall_enforced

    await set_paywall_enforced(db_session, False)
    response = await auth_client.post("/api/v1/calculator/estimate", json=_ACCESS_REQUEST)
    assert response.status_code == 200

