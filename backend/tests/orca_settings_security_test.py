"""Security boundary for opaque Orca machine settings."""

import pytest
from httpx import AsyncClient

from app.services.orca_settings_security import sanitize_orca_settings_for_storage


def test_machine_connection_data_is_removed_but_unknown_settings_round_trip() -> None:
    source = {
        "print_host": "192.0.2.10",
        "printhost_apikey": "secret",
        "flashforge_serial_number": "device-serial",
        "future_machine_field": {"keep": True},
    }

    sanitized = sanitize_orca_settings_for_storage(source, "machine")

    assert sanitized == {"future_machine_field": {"keep": True}}
    assert source["printhost_apikey"] == "secret"


def test_non_machine_settings_remain_lossless() -> None:
    settings = {"future_process_field": ["opaque", {"nested": True}]}

    assert sanitize_orca_settings_for_storage(settings, "process") == settings


@pytest.mark.asyncio
async def test_printer_profile_api_enforces_machine_connection_boundary(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/printer-profiles/",
        json={
            "name": "Connection boundary fixture",
            "slug": "connection-boundary-fixture",
            "orcaslicer_settings": {
                "print_host": "192.0.2.10",
                "printhost_apikey": "secret",
                "future_machine_field": {"keep": True},
            },
        },
    )

    assert created.status_code == 201
    profile = created.json()
    assert profile["orcaslicer_settings"] == {
        "future_machine_field": {"keep": True}
    }

    updated = await auth_client.patch(
        f"/api/v1/printer-profiles/{profile['id']}",
        json={
            "orcaslicer_settings": {
                "flashforge_serial_number": "device-serial",
                "another_future_field": "preserved",
            }
        },
    )

    assert updated.status_code == 200
    assert updated.json()["orcaslicer_settings"] == {
        "another_future_field": "preserved"
    }
