"""Why a local printer setup ended without pairing, as the plugin reports it."""

from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer_bridge_credential import PrinterBridgeCredential
from app.models.printer_bridge_receipt import PrinterBridgeReceipt
from app.services.printer_bridge_service import SETUP_ATTEMPT_KIND, _now

SOURCE = "setup-attempt-workstation-01"


async def _issued(auth_client: AsyncClient) -> tuple[int, int, str]:
    printer = await auth_client.post("/api/v1/physical-printers", json={"name": "Setup report printer"})
    assert printer.status_code == 201
    printer_id = printer.json()["id"]
    system = await auth_client.post(
        f"/api/v1/physical-printers/{printer_id}/material-systems",
        json={"name": "AMS", "provider": "bambu", "slot_count": 4},
    )
    assert system.status_code == 201
    system_id = system.json()["material_systems"][0]["id"]
    issued = await auth_client.post(
        f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}/pairing-code"
    )
    assert issued.status_code == 200
    return printer_id, system_id, issued.json()["pairing_code"]


def _report(code: str, stage: str, key: str, **extra) -> dict:
    return {
        "pairing_code": code,
        "provider": "bambu",
        "transport": "orca_plugin_lan",
        "source_instance_id": SOURCE,
        "stage": stage,
        "code": key,
        "plugin_version": "0.3.0",
        "platform": "windows",
        **extra,
    }


async def _status(auth_client: AsyncClient, printer_id: int, system_id: int) -> dict:
    response = await auth_client.get(f"/api/v1/printer-bridge/connections/{printer_id}/{system_id}")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_failed_setup_reason_reaches_the_printer_card(auth_client: AsyncClient):
    printer_id, system_id, code = await _issued(auth_client)

    sent = await auth_client.post(
        "/api/v1/printer-bridge/setup-attempt", json=_report(code, "report", "bambuNoReportSerial")
    )

    assert sent.status_code == 204
    status = await _status(auth_client, printer_id, system_id)
    assert status["paired"] is False
    assert status["last_setup_report"]["stage"] == "report"
    assert status["last_setup_report"]["code"] == "bambuNoReportSerial"
    assert status["last_setup_report"]["reported_at"]


@pytest.mark.asyncio
async def test_closing_the_window_does_not_hide_an_earlier_failure(auth_client: AsyncClient):
    printer_id, system_id, code = await _issued(auth_client)
    url = "/api/v1/printer-bridge/setup-attempt"

    await auth_client.post(url, json=_report(code, "auth", "bambuLanAuthRejected"))
    await auth_client.post(url, json=_report(code, "dialog", "cancelled"))

    assert (await _status(auth_client, printer_id, system_id))["last_setup_report"]["code"] == "bambuLanAuthRejected"


@pytest.mark.asyncio
async def test_a_try_after_closing_replaces_the_cancel(auth_client: AsyncClient):
    printer_id, system_id, code = await _issued(auth_client)
    url = "/api/v1/printer-bridge/setup-attempt"

    await auth_client.post(url, json=_report(code, "dialog", "cancelled"))
    assert (await _status(auth_client, printer_id, system_id))["last_setup_report"]["stage"] == "dialog"
    await auth_client.post(url, json=_report(code, "connect", "bambuUnreachable"))

    assert (await _status(auth_client, printer_id, system_id))["last_setup_report"]["code"] == "bambuUnreachable"


@pytest.mark.asyncio
async def test_an_expired_code_still_tells_why(auth_client: AsyncClient, db_session: AsyncSession):
    printer_id, system_id, code = await _issued(auth_client)
    credential = await db_session.scalar(select(PrinterBridgeCredential))
    assert credential is not None
    credential.pairing_expires_at = _now() - timedelta(minutes=1)
    await db_session.commit()

    await auth_client.post(
        "/api/v1/printer-bridge/setup-attempt", json=_report(code, "pair", "bambuPairingExpired")
    )

    assert (await _status(auth_client, printer_id, system_id))["last_setup_report"]["code"] == "bambuPairingExpired"


@pytest.mark.asyncio
async def test_unknown_code_or_other_provider_is_dropped_without_saying_so(
    auth_client: AsyncClient, db_session: AsyncSession
):
    _, _, code = await _issued(auth_client)
    url = "/api/v1/printer-bridge/setup-attempt"

    unknown = await auth_client.post(url, json=_report("ZZZZ-ZZZZ", "report", "bambuNoReport"))
    other = await auth_client.post(url, json=_report(code, "report", "bambuNoReport", provider="flashforge"))

    assert unknown.status_code == 204
    assert other.status_code == 204
    stored = await db_session.scalars(
        select(PrinterBridgeReceipt).where(PrinterBridgeReceipt.receipt_kind == SETUP_ATTEMPT_KIND)
    )
    assert stored.all() == []


@pytest.mark.asyncio
async def test_report_refuses_printer_details(auth_client: AsyncClient):
    _, _, code = await _issued(auth_client)

    response = await auth_client.post(
        "/api/v1/printer-bridge/setup-attempt",
        json=_report(code, "report", "bambuNoReport", host="192.168.1.50"),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_paired_printer_shows_no_old_failure(auth_client: AsyncClient):
    printer_id, system_id, code = await _issued(auth_client)
    await auth_client.post(
        "/api/v1/printer-bridge/setup-attempt", json=_report(code, "auth", "bambuLanAuthRejected")
    )

    paired = await auth_client.post("/api/v1/printer-bridge/pair", json={
        "pairing_code": code,
        "provider": "bambu",
        "transport": "orca_plugin_lan",
        "source_instance_id": SOURCE,
        "plugin_version": "0.3.0",
        "capabilities": ["read"],
    })

    assert paired.status_code == 200
    status = await _status(auth_client, printer_id, system_id)
    assert status["paired"] is True
    assert status["last_setup_report"] is None
