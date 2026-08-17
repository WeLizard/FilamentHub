"""Contracts for platform calculator defaults and explicit user overrides."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


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


@pytest.mark.asyncio
async def test_a_new_profile_abroad_is_priced_in_local_money_and_starts_empty(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    """A first visit from another country must not inherit the platform's rates.

    Without this, a shop in Germany opens the calculator and finds Russian hourly
    rates sitting under a euro sign — numbers wrong by the exchange rate that read
    as if the platform had recommended them.
    """
    configured = await admin_client.put(
        "/api/v1/admin/calculator-profile-defaults",
        json={
            "currency": "RUB",
            "printing_rate_per_hour": 170.0,
            "modeling_rate_per_hour": 934.0,
            "overhead_percent": 20.0,
            "printer_power_w": 350.0,
        },
    )
    assert configured.status_code == 200

    admin_user.country = "DE"
    await db_session.commit()

    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    body = created.json()

    assert body["currency"] == "EUR"
    assert body["printing_rate_per_hour"] == 0.0
    assert body["modeling_rate_per_hour"] == 0.0
    # Watts and percentages are not money and carry over untouched.
    assert body["overhead_percent"] == 20.0
    assert body["printer_power_w"] == 350.0


@pytest.mark.asyncio
async def test_country_row_currency_wins_over_the_country_default(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    """An admin who states a country's currency and rates is the authority on both."""
    configured = await admin_client.put(
        "/api/v1/admin/calculator-country-defaults",
        json={"countries": {"DE": {"currency": "EUR", "printing_rate_per_hour": 18.0}}},
    )
    assert configured.status_code == 200

    admin_user.country = "DE"
    await db_session.commit()

    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    assert created.json()["currency"] == "EUR"
    assert created.json()["printing_rate_per_hour"] == 18.0


@pytest.mark.asyncio
async def test_choosing_a_currency_does_not_import_another_country_economics(
    admin_client: AsyncClient,
) -> None:
    """Picking a currency in settings is the other way a profile first appears."""
    configured = await admin_client.put(
        "/api/v1/admin/calculator-profile-defaults",
        json={
            "currency": "RUB",
            "printing_rate_per_hour": 170.0,
            "modeling_rate_per_hour": 934.0,
        },
    )
    assert configured.status_code == 200

    switched = await admin_client.patch(
        "/api/v1/auth/me/preferences",
        json={"currency": "EUR"},
    )
    assert switched.status_code == 200

    profile = await admin_client.get("/api/v1/calculator/profile")
    assert profile.status_code == 200
    body = profile.json()
    assert body["currency"] == "EUR"
    assert body["modeling_rate_per_hour"] == 0.0
    assert body["printing_rate_per_hour"] == 0.0


@pytest.mark.asyncio
async def test_choosing_the_platform_currency_starts_from_platform_values(
    admin_client: AsyncClient,
) -> None:
    """The same path must still hand over the platform's economics when it fits.

    Creating the profile straight from the column defaults would look harmless here —
    everything is filled in — while quietly ignoring what an admin configured.
    """
    configured = await admin_client.put(
        "/api/v1/admin/calculator-profile-defaults",
        json={
            "currency": "RUB",
            "printing_rate_per_hour": 170.0,
            "modeling_rate_per_hour": 934.0,
        },
    )
    assert configured.status_code == 200

    switched = await admin_client.patch(
        "/api/v1/auth/me/preferences",
        json={"currency": "RUB"},
    )
    assert switched.status_code == 200

    profile = await admin_client.get("/api/v1/calculator/profile")
    assert profile.status_code == 200
    body = profile.json()
    assert body["currency"] == "RUB"
    assert body["printing_rate_per_hour"] == 170.0
    assert body["modeling_rate_per_hour"] == 934.0
