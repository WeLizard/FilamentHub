"""Tests for calculator endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_line import FilamentLine
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState


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
                "support_weight_g": 10,
                "support_weight_source": "gcode_extrusion_roles",
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
                "support_weight_g": 50,
                "support_weight_source": "gcode_extrusion_roles",
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
            "support_weight_g": 20.0,
            "support_cost": 16.0,
            "non_support_weight_g": 180.0,
            "non_support_cost": 144.0,
            "support_weight_source": "gcode_extrusion_roles",
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
            "support_weight_g": 100.0,
            "support_cost": 200.0,
            "non_support_weight_g": 0.0,
            "non_support_cost": 0.0,
            "support_weight_source": "gcode_extrusion_roles",
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



@pytest.mark.asyncio
async def test_rejected_estimate_is_not_counted_as_usage(
    admin_client: AsyncClient, monkeypatch
):
    """A request that fails validation is not a calculation, so it must leave the
    usage counters alone — otherwise the dashboard reports work nobody did."""
    recorded: list[tuple[int, str]] = []

    async def fake_record(user_id: int, pricing_method: str) -> None:
        recorded.append((user_id, pricing_method))

    monkeypatch.setattr(
        "app.api.v1.endpoints.calculator.record_calculator_estimate", fake_record
    )

    rejected = await admin_client.post(
        "/api/v1/calculator/estimate",
        json={"pricing_method": "by_time", "time_hours": 2},
    )
    assert rejected.status_code == 400
    assert recorded == []

    accepted = await admin_client.post(
        "/api/v1/calculator/estimate",
        json={
            "pricing_method": "by_weight",
            "weight_g": 100,
            "spool_price": 1500,
            "spool_weight_kg": 1,
        },
    )
    assert accepted.status_code == 200
    assert [method for _, method in recorded] == ["by_weight"]


@pytest.mark.asyncio
async def test_preflight_does_not_count_one_spool_twice_or_consume_it(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """One physical remainder must cover the whole job, not each line independently."""
    spool = UserSpool(
        user_id=admin_user.id,
        initial_weight_g=150,
        used_weight_g=0,
        state=UserSpoolState.active,
        price=300,
        source="manual",
        extra={"currency": "USD"},
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "safety_buffer_percent": 0,
            "lines": [
                {
                    "line_id": "tool-0",
                    "weight_g": 100,
                    "length_mm": 1000,
                    "evidence_source": "gcode",
                    "mapping_source": "automatic",
                    "mapping_confidence": "high",
                    "spool_ids": [spool.id],
                },
                {"line_id": "tool-1", "weight_g": 100, "spool_ids": [spool.id]},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient"
    assert [line["status"] for line in body["lines"]] == ["ready", "insufficient"]
    assert body["lines"][1]["selected_remaining_g"] == 50
    assert body["lines"][0]["evidence_source"] == "gcode"
    assert body["lines"][0]["mapping_source"] == "automatic"
    assert body["lines"][0]["mapping_confidence"] == "high"
    assert body["lines"][0]["required_length_mm"] == 1000
    first_allocation = body["lines"][0]["allocations"][0]
    assert first_allocation["sequence_index"] == 1
    assert first_allocation["remaining_source"] == "inventory_ledger"
    assert first_allocation["remaining_updated_at"]
    assert first_allocation["expected_purchase_cost"] == 200
    assert body["purchase_cost_by_currency"] == {"USD": 300}
    assert body["purchase_cost_complete"] is False

    await db_session.refresh(spool)
    assert spool.used_weight_g == 0


@pytest.mark.asyncio
async def test_preflight_does_not_turn_safety_buffer_into_phantom_consumption(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """A margin may make a later line risky, but it must not consume its base stock."""
    spool = UserSpool(
        user_id=admin_user.id,
        initial_weight_g=200,
        used_weight_g=0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "safety_buffer_percent": 20,
            "lines": [
                {"line_id": "first", "weight_g": 100, "spool_ids": [spool.id]},
                {"line_id": "second", "weight_g": 90, "spool_ids": [spool.id]},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready_at_risk"
    assert [line["status"] for line in body["lines"]] == ["ready", "ready_at_risk"]
    assert body["lines"][1]["selected_remaining_g"] == 100
    assert body["lines"][1]["shortfall_base_g"] == 0
    assert body["lines"][1]["shortfall_buffer_g"] == 8
    assert body["lines"][1]["expected_after_g"] == 10

    await db_session.refresh(spool)
    assert spool.used_weight_g == 0


@pytest.mark.asyncio
async def test_preflight_does_not_treat_stale_remaining_as_safe_stock(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """An old ledger value must ask for confirmation instead of promising a print."""
    spool = UserSpool(
        user_id=admin_user.id,
        initial_weight_g=200,
        used_weight_g=50,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    observed_at = datetime.now(timezone.utc) - timedelta(days=31)
    await db_session.execute(
        update(UserSpool)
        .where(UserSpool.id == spool.id)
        .values(updated_at=observed_at)
    )
    await db_session.commit()

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "safety_buffer_percent": 0,
            "lines": [
                {"line_id": "tool-0", "weight_g": 100, "spool_ids": [spool.id]}
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    line = body["lines"][0]
    allocation = line["allocations"][0]
    assert body["status"] == "needs_clarification"
    assert line["status"] == "needs_clarification"
    assert line["selected_remaining_g"] == 0
    assert line["expected_after_g"] == 0
    assert allocation["remaining_before_g"] == 150
    assert allocation["expected_consumption_g"] == 0
    assert allocation["remaining_status"] == "stale"
    assert allocation["remaining_evidence"] == "intake"
    assert "stale_remaining" in allocation["issues"]

    await db_session.refresh(spool)
    assert spool.used_weight_g == 50


@pytest.mark.asyncio
async def test_preflight_builds_a_sequential_spool_change_plan(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    spools = [
        UserSpool(
            user_id=admin_user.id,
            initial_weight_g=80,
            used_weight_g=0,
            state=UserSpoolState.active,
            price=240,
            source="manual",
            extra={"currency": "KZT"},
        ),
        UserSpool(
            user_id=admin_user.id,
            initial_weight_g=70,
            used_weight_g=0,
            state=UserSpoolState.active,
            price=350,
            source="manual",
            extra={"currency": "KZT"},
        ),
    ]
    db_session.add_all(spools)
    await db_session.commit()
    for spool in spools:
        await db_session.refresh(spool)

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "safety_buffer_percent": 10,
            "lines": [
                {
                    "line_id": "tool-0",
                    "weight_g": 120,
                    "spool_ids": [spool.id for spool in spools],
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    line = body["lines"][0]
    assert body["status"] == "ready_with_change"
    assert line["requires_spool_change"] is True
    assert line["change_count"] == 1
    assert [item["sequence_index"] for item in line["allocations"]] == [1, 2]
    assert [item["expected_consumption_g"] for item in line["allocations"]] == [80, 40]
    assert [item["expected_after_g"] for item in line["allocations"]] == [0, 30]
    assert body["purchase_cost_by_currency"] == {"KZT": 440}
    assert body["purchase_cost_complete"] is True

    for spool in spools:
        await db_session.refresh(spool)
        assert spool.used_weight_g == 0


@pytest.mark.asyncio
async def test_preflight_separates_exact_spools_from_reslice_candidates(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    brand = Brand(
        name=f"Preflight alternatives {admin_user.id}",
        slug=f"preflight-alternatives-{admin_user.id}",
    )
    db_session.add(brand)
    await db_session.flush()
    line = FilamentLine(brand_id=brand.id, name="ABS Basic")
    db_session.add(line)
    await db_session.flush()

    target = Filament(
        brand_id=brand.id,
        line_id=line.id,
        name="ABS Black",
        slug="abs-black",
        material_type="ABS",
        diameter=1.75,
    )
    same_line = Filament(
        brand_id=brand.id,
        line_id=line.id,
        name="ABS White",
        slug="abs-white",
        material_type="ABS",
        diameter=1.75,
    )
    same_type = Filament(
        brand_id=brand.id,
        name="ABS Other",
        slug="abs-other",
        material_type="abs",
        diameter=1.75,
    )
    wrong_diameter = Filament(
        brand_id=brand.id,
        name="ABS 2.85",
        slug="abs-285",
        material_type="ABS",
        diameter=2.85,
    )
    harder_material = Filament(
        brand_id=brand.id,
        name="ABS CF",
        slug="abs-cf",
        material_type="ABS",
        diameter=1.75,
        required_nozzle_hrc=50,
    )
    other_type = Filament(
        brand_id=brand.id,
        name="PLA Black",
        slug="pla-black",
        material_type="PLA",
        diameter=1.75,
    )
    filaments = [
        target,
        same_line,
        same_type,
        wrong_diameter,
        harder_material,
        other_type,
    ]
    db_session.add_all(filaments)
    await db_session.flush()

    selected = UserSpool(
        user_id=admin_user.id,
        filament_id=target.id,
        initial_weight_g=40,
        state=UserSpoolState.shelf,
    )
    exact = UserSpool(
        user_id=admin_user.id,
        filament_id=target.id,
        initial_weight_g=90,
        state=UserSpoolState.shelf,
    )
    replacement_spools = [
        UserSpool(
            user_id=admin_user.id,
            filament_id=filament.id,
            initial_weight_g=200,
            state=UserSpoolState.shelf,
        )
        for filament in [same_line, same_type, wrong_diameter, harder_material, other_type]
    ]
    db_session.add_all([selected, exact, *replacement_spools])
    await db_session.commit()

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "safety_buffer_percent": 20,
            "lines": [
                {
                    "line_id": "tool-0",
                    "filament_id": target.id,
                    "weight_g": 100,
                    "spool_ids": [selected.id],
                }
            ],
        },
    )

    assert response.status_code == 200
    suggestions = response.json()["lines"][0]["spool_suggestions"]
    assert [item["relation"] for item in suggestions] == [
        "same_filament",
        "same_line",
        "same_material_type",
    ]
    assert suggestions[0]["spool_id"] == exact.id
    assert suggestions[0]["requires_reslice"] is False
    assert suggestions[0]["coverage_target_g"] == 80
    assert suggestions[0]["covers_target"] is True
    assert all(item["requires_reslice"] for item in suggestions[1:])
    assert all(item["coverage_target_g"] == 120 for item in suggestions[1:])

    await db_session.refresh(selected)
    await db_session.refresh(exact)
    assert selected.used_weight_g == 0
    assert exact.used_weight_g == 0


@pytest.mark.asyncio
async def test_preflight_rejects_a_foreign_spool(
    admin_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    foreign_spool = UserSpool(
        user_id=auth_user.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.active,
        source="manual",
    )
    db_session.add(foreign_spool)
    await db_session.commit()
    await db_session.refresh(foreign_spool)

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "lines": [
                {
                    "line_id": "tool-0",
                    "weight_g": 100,
                    "spool_ids": [foreign_spool.id],
                }
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_SPOOL_NOT_ACCESSIBLE"


@pytest.mark.asyncio
async def test_preflight_reports_proven_machine_incompatibilities_without_blocking_material_result(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    brand = Brand(name="Compatibility brand", slug="compatibility-brand")
    catalog_printer = Printer(
        name="Compatibility printer",
        manufacturer="FilamentHub",
        model="One",
        slug="compatibility-printer",
        max_extruder_temp=260,
        active=True,
    )
    db_session.add_all([brand, catalog_printer])
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Abrasive PLA",
        slug="abrasive-pla-compatibility",
        material_type="PLA",
        diameter=1.75,
        required_nozzle_hrc=50,
    )
    profile = PrinterProfile(
        owner_user_id=admin_user.id,
        printer_id=catalog_printer.id,
        name="Compatibility printer 0.4 brass",
        slug="compatibility-printer-04-brass",
        setting_id="compatibility-printer-04-brass",
        nozzle_diameters=[0.4],
        orcaslicer_settings={"nozzle_hrc": [2]},
        active=True,
    )
    physical_printer = UserPrinterDevice(
        user_id=admin_user.id,
        printer_id=catalog_printer.id,
        name="Workshop printer",
    )
    db_session.add_all([filament, profile, physical_printer])
    await db_session.flush()
    db_session.add(
        UserPrinterProfileLink(
            user_id=admin_user.id,
            physical_printer_id=physical_printer.id,
            printer_profile_id=profile.id,
        )
    )
    await db_session.commit()

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "physical_printer_id": physical_printer.id,
            "print_jobs": [{
                "job_key": "plate-1",
                "print_time_seconds": 3600,
            }],
            "machine_evidence": [{
                "job_key": "plate-1",
                "printer_profile_id": profile.id,
                "printer_settings_id": profile.setting_id,
                "nozzle_diameter_mm": 0.4,
                "max_nozzle_temperature_c": 280,
                "source": "orca_plugin",
            }],
            "lines": [{
                "line_id": "plate-1-tool-0",
                "job_key": "plate-1",
                "filament_id": filament.id,
                "weight_g": 100,
                "spool_ids": [],
            }],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_clarification"
    compatibility = body["printer_compatibility"]
    assert compatibility["status"] == "incompatible"
    assert compatibility["physical_printer_name"] == "Workshop printer"
    checks = {item["kind"]: item for item in compatibility["checks"]}
    assert checks["nozzle_diameter"]["status"] == "compatible"
    assert checks["nozzle_hrc"]["status"] == "incompatible"
    assert checks["nozzle_hrc"]["available_values"] == [2.0]
    assert checks["hotend_temperature"]["status"] == "incompatible"
    assert checks["hotend_temperature"]["available_values"] == [260.0]


@pytest.mark.asyncio
async def test_preflight_keeps_missing_machine_capabilities_unknown(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    physical_printer = UserPrinterDevice(
        user_id=admin_user.id,
        name="Printer without proven configuration",
    )
    db_session.add(physical_printer)
    await db_session.commit()

    response = await admin_client.post(
        "/api/v1/calculator/preflight",
        json={
            "physical_printer_id": physical_printer.id,
            "machine_evidence": [{
                "nozzle_diameter_mm": 0.6,
                "max_nozzle_temperature_c": 250,
                "source": "gcode",
            }],
            "lines": [{
                "line_id": "manual",
                "weight_g": 10,
                "spool_ids": [],
            }],
        },
    )

    assert response.status_code == 200
    compatibility = response.json()["printer_compatibility"]
    assert compatibility["status"] == "unknown"
    assert [item["status"] for item in compatibility["checks"]] == ["unknown", "unknown"]
