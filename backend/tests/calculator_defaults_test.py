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


@pytest.mark.asyncio
async def test_profile_defaults_update_does_not_rewrite_subscription_settings(
    admin_client: AsyncClient,
) -> None:
    configured = await admin_client.post(
        "/api/v1/admin/calculator-settings",
        json={"paywall_enforced": True, "trial_days": 21},
    )
    assert configured.status_code == 200

    defaults = configured.json()["profile_defaults"]
    defaults["electricity_cost_per_kwh"] = 11.5
    updated = await admin_client.put(
        "/api/v1/admin/calculator-profile-defaults",
        json=defaults,
    )
    assert updated.status_code == 200
    assert updated.json()["electricity_cost_per_kwh"] == 11.5

    settings = await admin_client.get("/api/v1/admin/calculator-settings")
    assert settings.status_code == 200
    assert settings.json()["paywall_enforced"] is True
    assert settings.json()["trial_days"] == 21


@pytest.mark.asyncio
async def test_reset_defaults_keeps_money_out_of_another_currency(
    admin_client: AsyncClient,
) -> None:
    """Rates entered in one currency must not land in a profile billing in another."""
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200

    switched = await admin_client.put(
        "/api/v1/calculator/profile",
        json={"currency": "USD", "printing_rate_per_hour": 25.0, "overhead_percent": 12.0},
    )
    assert switched.status_code == 200
    assert switched.json()["currency"] == "USD"

    configured = await admin_client.put(
        "/api/v1/admin/calculator-profile-defaults",
        json={
            "currency": "RUB",
            "printing_rate_per_hour": 170.0,
            "electricity_cost_per_kwh": 6.0,
            "overhead_percent": 33.0,
            "printer_power_w": 420.0,
        },
    )
    assert configured.status_code == 200

    reset = await admin_client.post("/api/v1/calculator/profile/reset-defaults")
    assert reset.status_code == 200
    body = reset.json()
    # Roubles stay behind; watts and percentages mean the same everywhere.
    assert body["printing_rate_per_hour"] == 25.0
    assert body["overhead_percent"] == 33.0
    assert body["printer_power_w"] == 420.0
