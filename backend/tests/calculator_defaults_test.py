"""Contracts for platform calculator defaults and explicit user overrides."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_platform_defaults_seed_new_profile_without_overwriting_user_changes(
    admin_client: AsyncClient,
) -> None:
    configured = await admin_client.post(
        "/api/v1/admin/calculator-settings",
        json={
            "paywall_enforced": False,
            "trial_days": 14,
            "profile_defaults": {
                "electricity_cost_per_kwh": 8.75,
                "overhead_percent": 33,
            },
        },
    )
    assert configured.status_code == 200

    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    assert created.json()["electricity_cost_per_kwh"] == 8.75
    assert created.json()["overhead_percent"] == 33

    changed = await admin_client.put(
        "/api/v1/calculator/profile",
        json={"overhead_percent": 71, "seller_name": "Private workshop"},
    )
    assert changed.status_code == 200

    reconfigured = await admin_client.post(
        "/api/v1/admin/calculator-settings",
        json={
            "paywall_enforced": False,
            "trial_days": 14,
            "profile_defaults": {
                "electricity_cost_per_kwh": 9.25,
                "overhead_percent": 44,
            },
        },
    )
    assert reconfigured.status_code == 200

    preserved = await admin_client.get("/api/v1/calculator/profile")
    assert preserved.json()["overhead_percent"] == 71

    reset = await admin_client.post("/api/v1/calculator/profile/reset-defaults")
    assert reset.status_code == 200
    assert reset.json()["electricity_cost_per_kwh"] == 9.25
    assert reset.json()["overhead_percent"] == 44
    assert reset.json()["seller_name"] == "Private workshop"
