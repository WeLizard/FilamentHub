"""End-to-end API tests for the CRM-lite quote-to-order lifecycle."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared_quote import SharedQuote
from app.services import subscription_service


@pytest.fixture(autouse=True)
def restore_subscription_settings_cache():
    original = dict(subscription_service._settings_cache)
    yield
    subscription_service._settings_cache.clear()
    subscription_service._settings_cache.update(original)


def quote_payload() -> dict:
    return {
        "title": "Корпус датчика",
        "currency": "RUB",
        "valid_until": "2026-07-26",
        "new_customer": {
            "name": "ООО Тестовая мастерская",
            "email": "buyer@example.com",
            "phone": "+7 999 000-00-00",
        },
        "seller_snapshot": {"name": "Студия печати"},
        "customer_snapshot": {},
        "calculation_snapshot": {"source": "gcode", "cost_total": 2500},
        "payment_terms": "50% предоплата",
        "disclaimer_mode": "not_offer",
        "tax_total": 0,
        "html_content": "<html><body><h1>{{CRM_QUOTE_NUMBER}}</h1></body></html>",
        "lines": [
            {
                "title": "Корпус",
                "details": ["PETG", "Вес: 120 г"],
                "quantity": 2,
                "unit": "pcs",
                "unit_price": 1250,
                "source_data": {"job_key": "job-1"},
            }
        ],
    }


@pytest.mark.asyncio
async def test_quote_acceptance_creates_order_and_preserves_version(
    auth_client,
    db_session: AsyncSession,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)

    create_response = await auth_client.post("/api/v1/crm/quotes", json=quote_payload())
    assert create_response.status_code == 201, create_response.text
    quote = create_response.json()
    quote_id = quote["id"]
    assert quote["status"] == "draft"
    assert quote["customer"]["name"] == "ООО Тестовая мастерская"
    assert quote["current_version"]["version_number"] == 1
    assert quote["current_version"]["grand_total"] == 2500.0
    assert quote["current_version"]["lines"][0]["details"] == ["PETG", "Вес: 120 г"]

    sent_response = await auth_client.post(
        f"/api/v1/crm/quotes/{quote_id}/status", json={"status": "sent"}
    )
    assert sent_response.status_code == 200, sent_response.text
    assert sent_response.json()["status"] == "sent"

    pending_summary = (await auth_client.get("/api/v1/crm/summary")).json()
    assert pending_summary["amount_awaiting_decision"] == {"RUB": 2500.0}

    share_response = await auth_client.post(f"/api/v1/crm/quotes/{quote_id}/share")
    assert share_response.status_code == 200, share_response.text
    shared = await db_session.scalar(
        select(SharedQuote).where(SharedQuote.uuid == share_response.json()["uuid"])
    )
    assert shared is not None
    assert quote["number"] in shared.html_content
    assert "{{CRM_QUOTE_NUMBER}}" not in shared.html_content

    accepted_response = await auth_client.post(
        f"/api/v1/crm/quotes/{quote_id}/status", json={"status": "accepted"}
    )
    assert accepted_response.status_code == 200, accepted_response.text
    accepted = accepted_response.json()
    assert accepted["status"] == "accepted"
    assert accepted["order"]["status"] == "new"
    assert accepted["order"]["total"] == 2500.0
    assert accepted["order"]["number"].startswith("ЗК-")

    orders_response = await auth_client.get("/api/v1/crm/orders")
    assert orders_response.status_code == 200
    assert orders_response.json()["total"] == 1

    summary_response = await auth_client.get("/api/v1/crm/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["customers_total"] == 1
    assert summary["quotes_accepted"] == 1
    assert summary["orders_active"] == 1
    assert summary["accepted_amount"] == {"RUB": 2500.0}


@pytest.mark.asyncio
async def test_new_version_reopens_sent_quote_but_accepted_quote_is_locked(
    auth_client,
    db_session: AsyncSession,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)
    quote = (await auth_client.post("/api/v1/crm/quotes", json=quote_payload())).json()
    quote_id = quote["id"]
    await auth_client.post(f"/api/v1/crm/quotes/{quote_id}/status", json={"status": "sent"})

    version_payload = {
        key: value
        for key, value in quote_payload().items()
        if key
        in {
            "seller_snapshot",
            "customer_snapshot",
            "calculation_snapshot",
            "payment_terms",
            "disclaimer_mode",
            "tax_total",
            "html_content",
            "lines",
        }
    }
    version_payload["lines"][0]["unit_price"] = 1400
    version_response = await auth_client.post(
        f"/api/v1/crm/quotes/{quote_id}/versions", json=version_payload
    )
    assert version_response.status_code == 201, version_response.text
    revised = version_response.json()
    assert revised["status"] == "draft"
    assert revised["current_version"]["version_number"] == 2
    assert revised["current_version"]["grand_total"] == 2800.0
    assert len(revised["versions"]) == 2

    await auth_client.post(f"/api/v1/crm/quotes/{quote_id}/status", json={"status": "accepted"})
    locked_response = await auth_client.post(
        f"/api/v1/crm/quotes/{quote_id}/versions", json=version_payload
    )
    assert locked_response.status_code == 409
    assert locked_response.json()["detail"]["code"] == "ERR_CRM_QUOTE_LOCKED"


@pytest.mark.asyncio
async def test_invalid_quote_transition_is_rejected(
    auth_client,
    db_session: AsyncSession,
) -> None:
    await subscription_service.set_paywall_enforced(db_session, False)
    quote = (await auth_client.post("/api/v1/crm/quotes", json=quote_payload())).json()

    response = await auth_client.post(
        f"/api/v1/crm/quotes/{quote['id']}/status", json={"status": "expired"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_CRM_INVALID_STATUS_TRANSITION"
