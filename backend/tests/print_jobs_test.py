"""Expensive invariants of the provider-neutral print history."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.filament import Filament
from app.models.orca_slice_report import OrcaSliceReport
from app.models.user_spool import UserSpool, UserSpoolState


@pytest.mark.asyncio
async def test_manual_print_job_keeps_references_timeline_and_snapshots(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user,
) -> None:
    printer_response = await auth_client.post(
        "/api/v1/physical-printers", json={"name": "Workshop Voron"}
    )
    assert printer_response.status_code == 201
    printer_id = printer_response.json()["id"]

    brand = Brand(name="History Brand", slug="history-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="History PETG",
        slug="history-petg",
        material_type="PETG",
        color_name="Blue",
        color_hex="#1234AB",
    )
    db_session.add(filament)
    await db_session.flush()
    spool = UserSpool(
        user_id=auth_user.id,
        filament_id=filament.id,
        initial_weight_g=1000,
        used_weight_g=100,
        state=UserSpoolState.shelf,
    )
    calculation = CalculatorHistoryEntry(
        user_id=auth_user.id,
        title="Three brackets",
        pricing_method="combined",
        request_data={},
        result_data={},
        parsed_gcode={
            "format": "calculator_batch_v1",
            "jobs": [{"job_key": "plate-1", "parsed_gcode": {}}],
        },
    )
    db_session.add_all([spool, calculation])
    await db_session.flush()
    slice_report = OrcaSliceReport(
        user_id=auth_user.id,
        physical_printer_id=printer_id,
        file_name="brackets.gcode",
        dedupe_key="print-job-history-slice",
    )
    db_session.add(slice_report)
    await db_session.commit()

    payload = {
        "idempotency_key": "manual-job-0001",
        "title": "Three brackets",
        "physical_printer_id": printer_id,
        "calculator_history_id": calculation.id,
        "calculator_job_key": "plate-1",
        "orca_slice_report_id": slice_report.id,
        "estimated_duration_s": 3600,
        "materials": [
            {
                "spool_id": spool.id,
                "material_line_key": "tool:0",
                "tool_index": 0,
                "planned_weight_g": 42.5,
            }
        ],
    }
    created = await auth_client.post("/api/v1/print-jobs", json=payload)
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "prepared"
    assert job["file_name"] == "brackets.gcode"
    assert job["calculation_title"] == "Three brackets"
    assert job["confirmed_consumption_g"] == 0
    assert job["materials"][0]["spool_name"] == "History Brand · History PETG"
    assert [event["status"] for event in job["events"]] == ["prepared"]

    replay = await auth_client.post("/api/v1/print-jobs", json=payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == job["id"]
    conflict = await auth_client.post(
        "/api/v1/print-jobs", json={**payload, "title": "Different payload"}
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ERR_PRINT_JOB_REPLAY_CONFLICT"

    for index, next_status in enumerate(("printing", "paused", "printing", "completed")):
        transitioned = await auth_client.post(
            f"/api/v1/print-jobs/{job['id']}/events",
            json={
                "idempotency_key": f"transition-{index:02d}",
                "status": next_status,
            },
        )
        assert transitioned.status_code == 200
    completed = transitioned.json()
    assert completed["status"] == "completed"
    assert completed["started_at"] is not None
    assert completed["finished_at"] is not None

    invalid = await auth_client.post(
        f"/api/v1/print-jobs/{job['id']}/events",
        json={"idempotency_key": "transition-after-terminal", "status": "printing"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "ERR_PRINT_JOB_INVALID_TRANSITION"

    deleted_slice = await auth_client.delete(f"/api/v1/orcaslicer/slices/{slice_report.id}")
    assert deleted_slice.status_code == 204
    deleted_spool = await auth_client.delete(f"/api/v1/spools/{spool.id}")
    assert deleted_spool.status_code == 204
    preserved_sources = await auth_client.get(f"/api/v1/print-jobs/{job['id']}")
    assert preserved_sources.status_code == 200
    assert preserved_sources.json()["orca_slice_report_id"] is None
    assert preserved_sources.json()["file_name"] == "brackets.gcode"
    assert preserved_sources.json()["materials"][0]["spool_id"] is None
    assert preserved_sources.json()["materials"][0]["spool_name"] == (
        "History Brand · History PETG"
    )

    deleted_printer = await auth_client.delete(f"/api/v1/physical-printers/{printer_id}")
    assert deleted_printer.status_code == 204
    preserved = await auth_client.get(f"/api/v1/print-jobs/{job['id']}")
    assert preserved.status_code == 200
    assert preserved.json()["physical_printer_id"] is None
    assert preserved.json()["printer_name"] == "Workshop Voron"


@pytest.mark.asyncio
async def test_print_job_rejects_a_spool_owned_by_another_account(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    auth_user,
) -> None:
    from app.models.user import User

    printer = await auth_client.post("/api/v1/physical-printers", json={"name": "Private printer"})
    other = User(
        email="another-print-owner@example.com",
        username="anotherprintowner",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
    )
    db_session.add(other)
    await db_session.flush()
    foreign_spool = UserSpool(
        user_id=other.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
    )
    db_session.add(foreign_spool)
    await db_session.commit()

    response = await auth_client.post(
        "/api/v1/print-jobs",
        json={
            "idempotency_key": "foreign-spool-job",
            "title": "Must not open the other inventory",
            "physical_printer_id": printer.json()["id"],
            "materials": [{"spool_id": foreign_spool.id}],
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_ACCESS_DENIED"
