"""Versioned calculator economics readiness and field provenance contracts."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calculator_profile import UserCalculatorProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.services.printer_economics_service import resolve_economics


async def _printer(
    db: AsyncSession, user: User, **fields: object
) -> UserPrinterDevice:
    printer = UserPrinterDevice(
        user_id=user.id,
        name="Readiness printer",
        device_fingerprint=None,
        supports_hh=False,
        **fields,
    )
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    return printer


async def _explicit_account_profile(
    db: AsyncSession, user: User
) -> UserCalculatorProfile:
    profile = UserCalculatorProfile(
        user_id=user.id,
        currency="RUB",
        electricity_cost_per_kwh=0.0,
        printer_power_w=350.0,
        printing_rate_per_hour=170.0,
        amortization_rate_per_hour=0.0,
        economics_field_sources={
            "currency": "account_explicit",
            "electricity_cost_per_kwh": "account_explicit",
            "printer_power_w": "account_explicit",
            "printing_rate_per_hour": "account_explicit",
            "amortization_rate_per_hour": "account_explicit",
        },
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def _readiness_fields(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    readiness = payload["readiness"]
    assert isinstance(readiness, dict)
    required_fields = readiness["required_fields"]
    assert isinstance(required_fields, list)
    return {str(item["key"]): item for item in required_fields}


@pytest.mark.asyncio
async def test_fresh_and_existing_account_profiles_expose_seeded_readiness(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    existing = await admin_client.get("/api/v1/calculator/profile")

    assert created.status_code == 200
    assert existing.status_code == 200
    for response in (created, existing):
        readiness = response.json()["economics_readiness"]
        assert readiness["version"] == 1
        assert readiness["status"] == "partial"
        assert readiness["money_currency"] == response.json()["currency"]
        assert "platform_default_used" in readiness["reasons"]
        assert {item["source"] for item in readiness["required_fields"]} == {
            "platform_default"
        }


@pytest.mark.asyncio
async def test_account_profile_partial_update_marks_only_supplied_fields_explicit(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200

    updated = await admin_client.put(
        "/api/v1/calculator/profile", json={"printing_rate_per_hour": 240.0}
    )
    assert updated.status_code == 200

    profile = await db_session.scalar(
        select(UserCalculatorProfile).where(
            UserCalculatorProfile.user_id == admin_user.id
        )
    )
    assert profile is not None
    assert profile.economics_field_sources["printing_rate_per_hour"] == "account_explicit"
    assert profile.economics_field_sources["electricity_cost_per_kwh"] == "platform_default"

    readiness_fields = {
        item["key"]: item
        for item in updated.json()["economics_readiness"]["required_fields"]
    }
    assert readiness_fields["machine_hour_rate"]["source"] == "account_explicit"
    assert readiness_fields["electricity_cost_per_kwh"]["source"] == "platform_default"
    assert updated.json()["economics_readiness"]["status"] == "partial"


@pytest.mark.asyncio
async def test_account_zero_semantics_distinguish_rate_from_valid_zero_costs(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    configured = await admin_client.put(
        "/api/v1/calculator/profile",
        json={
            "currency": "RUB",
            "printing_rate_per_hour": 200.0,
            "electricity_cost_per_kwh": 0.0,
            "printer_power_w": 300.0,
            "amortization_rate_per_hour": 0.0,
        },
    )
    assert configured.status_code == 200
    assert configured.json()["economics_readiness"]["status"] == "configured"

    zero_rate = await admin_client.put(
        "/api/v1/calculator/profile", json={"printing_rate_per_hour": 0.0}
    )
    assert zero_rate.status_code == 200
    readiness = zero_rate.json()["economics_readiness"]
    assert readiness["status"] == "incomplete"
    rate_field = next(
        item for item in readiness["required_fields"] if item["key"] == "machine_hour_rate"
    )
    assert rate_field == {
        "key": "machine_hour_rate",
        "value": 0.0,
        "source": "account_explicit",
        "source_currency": "RUB",
        "usable": False,
        "missing_reason": "non_positive",
    }


@pytest.mark.asyncio
async def test_currency_preference_marks_currency_only_as_account_explicit(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    changed = await admin_client.patch(
        "/api/v1/auth/me/preferences", json={"currency": "EUR"}
    )
    assert changed.status_code == 200

    profile = await db_session.scalar(
        select(UserCalculatorProfile).where(
            UserCalculatorProfile.user_id == admin_user.id
        )
    )
    assert profile is not None
    assert profile.economics_field_sources["currency"] == "account_explicit"
    assert profile.economics_field_sources["printer_power_w"] == "platform_default"
    assert profile.economics_field_sources["printing_rate_per_hour"] == "platform_default"


@pytest.mark.asyncio
async def test_manual_printer_patch_owns_provenance_and_clear_removes_it(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await _explicit_account_profile(db_session, auth_user)
    printer = await _printer(db_session, auth_user)

    saved = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={
            "economics_currency": "RUB",
            "average_power_watts": 420.0,
            "purchase_cost": 0.0,
            "maintenance_cost_per_hour": 0.0,
            "machine_hour_rate": 90.0,
            "field_sources": {"machine_hour_rate": "catalog_estimate"},
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["readiness"]["status"] == "configured"
    assert body["applied_sources"]["machine_hour_rate"] == "printer_explicit"
    assert body["applied_sources"]["maintenance_per_hour"] == "printer_explicit"

    await db_session.refresh(printer)
    assert printer.economics_field_sources["machine_hour_rate"] == "printer_explicit"
    assert "field_sources" not in printer.economics_field_sources

    cleared = await auth_client.patch(
        f"/api/v1/physical-printers/{printer.id}/economics",
        json={"average_power_watts": None},
    )
    assert cleared.status_code == 200
    await db_session.refresh(printer)
    assert "average_power_watts" not in printer.economics_field_sources


@pytest.mark.asyncio
async def test_server_applies_only_physical_suggestions_with_catalog_provenance(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await _explicit_account_profile(db_session, auth_user)
    printer = await _printer(
        db_session,
        auth_user,
        economics_currency="RUB",
        machine_hour_rate=90.0,
        maintenance_cost_per_hour=0.0,
        economics_field_sources={
            "economics_currency": "printer_explicit",
            "machine_hour_rate": "printer_explicit",
            "maintenance_cost_per_hour": "printer_explicit",
        },
    )

    applied = await auth_client.post(
        f"/api/v1/physical-printers/{printer.id}/economics/apply-suggestion",
        json={"usage": "intensive", "fields": ["average_power_watts", "useful_life_hours"]},
    )
    assert applied.status_code == 200
    body = applied.json()
    assert body["average_power_watts"] > 0
    assert body["useful_life_hours"] == 12000
    assert body["maintenance_cost_per_hour"] == 0.0
    assert body["applied_sources"]["printer_power_w"] == "catalog_estimate"
    assert body["readiness"]["status"] == "partial"
    assert "catalog_estimate_used" in body["readiness"]["reasons"]

    rejected_money = await auth_client.post(
        f"/api/v1/physical-printers/{printer.id}/economics/apply-suggestion",
        json={"fields": ["maintenance_cost_per_hour"]},
    )
    assert rejected_money.status_code == 422


@pytest.mark.asyncio
async def test_residual_value_participates_in_depreciation_provenance(
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await _explicit_account_profile(db_session, auth_user)
    printer = await _printer(
        db_session,
        auth_user,
        economics_currency="RUB",
        purchase_cost=100_000.0,
        residual_value=10_000.0,
        useful_life_hours=9000,
        maintenance_cost_per_hour=0.0,
        machine_hour_rate=100.0,
        average_power_watts=300.0,
        economics_field_sources={
            "economics_currency": "printer_explicit",
            "purchase_cost": "printer_explicit",
            "residual_value": "printer_explicit",
            "useful_life_hours": "catalog_estimate",
            "maintenance_cost_per_hour": "printer_explicit",
            "machine_hour_rate": "printer_explicit",
            "average_power_watts": "printer_explicit",
        },
    )

    resolved = await resolve_economics(db_session, printer)

    assert resolved.depreciation_per_hour == 10.0
    assert resolved.applied_sources["depreciation_per_hour"] == "catalog_estimate"
    assert resolved.applied_sources["machine_wear_per_hour"] == "catalog_estimate"
    assert resolved.readiness is not None
    assert resolved.readiness.status == "partial"


@pytest.mark.asyncio
async def test_currency_mismatch_uses_compatible_account_money_but_keeps_printer_power(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await _explicit_account_profile(db_session, auth_user)
    printer = await _printer(
        db_session,
        auth_user,
        economics_currency="USD",
        machine_hour_rate=50.0,
        maintenance_cost_per_hour=2.0,
        average_power_watts=410.0,
        economics_field_sources={
            "economics_currency": "printer_explicit",
            "machine_hour_rate": "printer_explicit",
            "maintenance_cost_per_hour": "printer_explicit",
            "average_power_watts": "printer_explicit",
        },
    )

    response = await auth_client.get(
        f"/api/v1/physical-printers/{printer.id}/economics"
    )
    assert response.status_code == 200
    body = response.json()
    fields = _readiness_fields(body)
    assert body["readiness"]["status"] == "partial"
    assert "currency_mismatch" in body["readiness"]["reasons"]
    assert fields["machine_hour_rate"]["value"] == 170.0
    assert fields["machine_hour_rate"]["source"] == "account_explicit"
    assert fields["printer_power_w"]["value"] == 410.0
    assert fields["printer_power_w"]["source"] == "printer_explicit"
    assert body["applied_sources"]["currency"] == "account_explicit"


@pytest.mark.asyncio
async def test_one_power_component_cannot_replace_a_complete_account_total(
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    await _explicit_account_profile(db_session, auth_user)
    printer = await _printer(
        db_session,
        auth_user,
        power_hotend_w=100.0,
        economics_field_sources={"power_hotend_w": "printer_explicit"},
    )

    resolved = await resolve_economics(db_session, printer)

    assert resolved.printer_power_w == 350.0
    assert resolved.sources["power"] == "account"
    assert resolved.applied_sources["printer_power_w"] == "account_explicit"
    assert resolved.readiness is not None
    assert resolved.readiness.status == "partial"
    assert "incomplete_pair" in resolved.readiness.reasons


@pytest.mark.asyncio
async def test_maintenance_only_uses_whole_account_wear_fallback(
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    profile = await _explicit_account_profile(db_session, auth_user)
    profile.amortization_rate_per_hour = 16.0
    await db_session.commit()
    printer = await _printer(
        db_session,
        auth_user,
        economics_currency="RUB",
        maintenance_cost_per_hour=0.0,
        economics_field_sources={
            "economics_currency": "printer_explicit",
            "maintenance_cost_per_hour": "printer_explicit",
        },
    )

    resolved = await resolve_economics(db_session, printer)

    assert resolved.amortization_rate_per_hour == 16.0
    assert resolved.maintenance_per_hour == 0.0
    assert resolved.sources["wear"] == "account"
    assert resolved.applied_sources["machine_wear_per_hour"] == "account_explicit"
    assert resolved.readiness is not None
    assert resolved.readiness.status == "partial"
    assert "incomplete_pair" in resolved.readiness.reasons


@pytest.mark.asyncio
async def test_maintenance_only_without_account_wear_is_incomplete(
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    printer = await _printer(
        db_session,
        auth_user,
        economics_currency="RUB",
        average_power_watts=300.0,
        maintenance_cost_per_hour=0.0,
        machine_hour_rate=100.0,
        economics_field_sources={
            "economics_currency": "printer_explicit",
            "average_power_watts": "printer_explicit",
            "maintenance_cost_per_hour": "printer_explicit",
            "machine_hour_rate": "printer_explicit",
        },
    )

    resolved = await resolve_economics(db_session, printer)

    assert resolved.sources["wear"] == "none"
    assert resolved.readiness is not None
    assert resolved.readiness.status == "incomplete"
    wear = next(
        field
        for field in resolved.readiness.required_fields
        if field.key == "machine_wear_per_hour"
    )
    assert wear.value is None
    assert wear.usable is False
    assert wear.missing_reason == "missing"
    assert "incomplete_pair" in resolved.readiness.reasons


@pytest.mark.asyncio
async def test_estimate_preserves_explicit_zero_pricing_adjustments(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/v1/calculator/estimate",
        json={
            "pricing_method": "combined",
            "quantity": 1,
            "time_hours": 1,
            "printing_rate_per_hour": 100.37,
            "amortization_rate_per_hour": 0,
            "electricity_cost_per_kwh": 0,
            "printer_power_w": 350,
            "overhead_percent": 0,
            "markup_percent": 0,
            "tax_rate_percent": 0,
            "round_to_nearest": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["cost_printing"] == 100.37
    assert body["cost_amortization"] == 0.0
    assert body["cost_electricity"] == 0.0
    assert body["cost_overhead"] == 0.0
    assert body["cost_markup"] == 0.0
    assert body["cost_tax"] == 0.0
    assert body["cost_final"] == 100.37


@pytest.mark.parametrize(
    ("rounding_mode", "expected"),
    [("up", 110.0), ("nearest", 100.0), ("down", 100.0)],
)
@pytest.mark.asyncio
async def test_estimate_applies_each_rounding_mode(
    admin_client: AsyncClient,
    rounding_mode: str,
    expected: float,
) -> None:
    response = await admin_client.post(
        "/api/v1/calculator/estimate",
        json={
            "pricing_method": "combined",
            "quantity": 1,
            "time_hours": 1,
            "printing_rate_per_hour": 100.37,
            "overhead_percent": 0,
            "markup_percent": 0,
            "tax_rate_percent": 0,
            "round_to_nearest": 10,
            "rounding_mode": rounding_mode,
        },
    )

    assert response.status_code == 200
    assert response.json()["cost_final"] == expected


@pytest.mark.asyncio
async def test_readiness_keeps_non_decimal_currency_as_code_without_conversion(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    response = await admin_client.put(
        "/api/v1/calculator/profile",
        json={
            "currency": "JPY",
            "printing_rate_per_hour": 200.0,
            "electricity_cost_per_kwh": 8.0,
            "printer_power_w": 300.0,
            "amortization_rate_per_hour": 10.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "JPY"
    assert body["printing_rate_per_hour"] == 200.0
    assert body["electricity_cost_per_kwh"] == 8.0
    assert body["economics_readiness"]["money_currency"] == "JPY"
    assert {
        item["source_currency"]
        for item in body["economics_readiness"]["required_fields"]
        if item["key"] != "printer_power_w"
    } == {"JPY"}


@pytest.mark.asyncio
async def test_profile_currency_only_change_clears_old_money_and_keeps_physical_fields(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    seeded = await admin_client.put(
        "/api/v1/calculator/profile",
        json={
            "printing_rate_per_hour": 210.0,
            "electricity_cost_per_kwh": 7.0,
            "modeling_rate_per_hour": 900.0,
            "round_to_nearest": 10,
            "printer_purchase_price": 80_000.0,
            "maintenance_cost_per_hour": 4.0,
            "printer_power_w": 444.0,
            "printer_useful_hours": 9000,
            "overhead_percent": 17.0,
        },
    )
    assert seeded.status_code == 200

    changed = await admin_client.put(
        "/api/v1/calculator/profile", json={"currency": "USD"}
    )

    assert changed.status_code == 200
    body = changed.json()
    assert body["currency"] == "USD"
    for field_name in (
        "printing_rate_per_hour",
        "electricity_cost_per_kwh",
        "modeling_rate_per_hour",
        "round_to_nearest",
        "printer_purchase_price",
        "maintenance_cost_per_hour",
    ):
        assert body[field_name] == 0
    assert body["printer_power_w"] == 444.0
    assert body["printer_useful_hours"] == 9000
    assert body["overhead_percent"] == 17.0

    profile = await db_session.scalar(
        select(UserCalculatorProfile).where(
            UserCalculatorProfile.user_id == admin_user.id
        )
    )
    assert profile is not None
    assert profile.economics_field_sources["currency"] == "account_explicit"
    assert profile.economics_field_sources["printer_power_w"] == "account_explicit"
    assert "printing_rate_per_hour" not in profile.economics_field_sources
    assert "round_to_nearest" not in profile.economics_field_sources


@pytest.mark.asyncio
async def test_profile_currency_change_keeps_money_replaced_in_same_request(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200

    changed = await admin_client.put(
        "/api/v1/calculator/profile",
        json={
            "currency": "JPY",
            "printing_rate_per_hour": 2500.0,
            "electricity_cost_per_kwh": 30.0,
            "round_to_nearest": 100,
        },
    )

    assert changed.status_code == 200
    body = changed.json()
    assert body["currency"] == "JPY"
    assert body["printing_rate_per_hour"] == 2500.0
    assert body["electricity_cost_per_kwh"] == 30.0
    assert body["round_to_nearest"] == 100
    fields = {
        item["key"]: item
        for item in body["economics_readiness"]["required_fields"]
    }
    assert fields["machine_hour_rate"]["source"] == "account_explicit"
    assert fields["machine_hour_rate"]["source_currency"] == "JPY"


@pytest.mark.asyncio
async def test_preferences_currency_change_clears_incompatible_account_money(
    admin_client: AsyncClient,
) -> None:
    created = await admin_client.get("/api/v1/calculator/profile")
    assert created.status_code == 200
    configured = await admin_client.put(
        "/api/v1/calculator/profile",
        json={
            "printing_rate_per_hour": 180.0,
            "electricity_cost_per_kwh": 6.5,
            "round_to_nearest": 10,
            "printer_power_w": 390.0,
        },
    )
    assert configured.status_code == 200

    preference = await admin_client.patch(
        "/api/v1/auth/me/preferences", json={"currency": "EUR"}
    )
    profile = await admin_client.get("/api/v1/calculator/profile")

    assert preference.status_code == 200
    assert profile.status_code == 200
    body = profile.json()
    assert body["currency"] == "EUR"
    assert body["printing_rate_per_hour"] == 0.0
    assert body["electricity_cost_per_kwh"] == 0.0
    assert body["round_to_nearest"] == 0
    assert body["printer_power_w"] == 390.0
