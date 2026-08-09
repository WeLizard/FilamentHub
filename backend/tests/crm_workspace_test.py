"""End-to-end API tests for the CRM-lite quote-to-order lifecycle."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import decrypt_field
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
async def test_another_workspace_cannot_reach_this_one(
    auth_client,
    db_session: AsyncSession,
) -> None:
    """A quote and its customer belong to one workspace only.

    The CRM holds prices and encrypted customer details, and every endpoint
    filters by owner in its own loader. One shared helper losing that filter
    would open the whole workspace, so the boundary is checked from outside.
    """
    from app.core.security import create_access_token
    from app.models.user import User
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_TERMS_VERSION,
    )

    await subscription_service.set_paywall_enforced(db_session, False)

    quote = (await auth_client.post("/api/v1/crm/quotes", json=quote_payload())).json()
    customer_id = quote["customer"]["id"]

    stranger = User(
        email="crm-stranger@example.com",
        username="crm_stranger",
        password_hash="not-used-in-this-test",
        active=True,
        email_verified=True,
        # Without the accepted documents the legal gate answers 403 first, and
        # the ownership check below would never be reached.
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(stranger)
    await db_session.commit()

    # auth_client is the shared client object: swapping the header is what makes
    # the next call come from somebody else. Restored below on purpose.
    owner_auth = auth_client.headers["Authorization"]
    auth_client.headers["Authorization"] = (
        f"Bearer {create_access_token({'sub': stranger.email})}"
    )

    assert (await auth_client.get(f"/api/v1/crm/quotes/{quote['id']}")).status_code == 404
    assert (
        await auth_client.patch(
            f"/api/v1/crm/quotes/{quote['id']}", json={"payment_terms": "предоплата 100%"}
        )
    ).status_code == 404
    assert (
        await auth_client.patch(
            f"/api/v1/crm/customers/{customer_id}", json={"name": "Чужое имя"}
        )
    ).status_code == 404
    assert (await auth_client.get("/api/v1/crm/quotes")).json()["items"] == []
    assert (await auth_client.get("/api/v1/crm/customers")).json()["items"] == []

    # The owner still sees it: otherwise the 404s above would prove nothing but
    # a broken token.
    auth_client.headers["Authorization"] = owner_auth
    assert (await auth_client.get(f"/api/v1/crm/quotes/{quote['id']}")).status_code == 200


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
    published = decrypt_field(shared.html_content)
    assert quote["number"] in published
    assert "{{CRM_QUOTE_NUMBER}}" not in published

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


@pytest.mark.asyncio
async def test_customer_details_are_unreadable_in_the_database(
    auth_client, db_session: AsyncSession
):
    """A leaked dump must not hand over the contacts a person keeps here."""
    from app.models.crm import CrmCustomer

    await subscription_service.set_paywall_enforced(db_session, False)

    created = await auth_client.post(
        "/api/v1/crm/customers",
        json={
            "name": "ООО «Ромашка»",
            "contact_name": "Иван Петров",
            "email": "ivan@romashka.example",
            "phone": "+7 900 000-00-00",
            "inn": "7701234567",
            "address": "Москва, ул. Ленина, 1",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "ООО «Ромашка»"
    assert body["phone"] == "+7 900 000-00-00"

    stored = (await db_session.execute(select(CrmCustomer))).scalars().one()
    for column in ("name", "contact_name", "email", "phone", "inn", "address"):
        raw = getattr(stored, column)
        assert raw.startswith("fh1:"), column
    assert "Ромашка" not in stored.name
    assert "7701234567" not in stored.inn


def test_encrypted_customer_fields_have_unbounded_storage() -> None:
    """Plaintext validation limits must not constrain encrypted storage."""
    from sqlalchemy import Text

    from app.models.crm import CrmCustomer

    for column_name in (
        "name",
        "contact_name",
        "email",
        "phone",
        "inn",
        "address",
        "note",
    ):
        assert isinstance(CrmCustomer.__table__.c[column_name].type, Text), column_name


@pytest.mark.asyncio
async def test_customer_search_still_finds_what_the_database_cannot_read(
    auth_client, db_session: AsyncSession
):
    await subscription_service.set_paywall_enforced(db_session, False)

    await auth_client.post(
        "/api/v1/crm/customers",
        json={"name": "ООО «Ромашка»", "phone": "+7 900 111-22-33"},
    )
    await auth_client.post("/api/v1/crm/customers", json={"name": "ЗАО «Василёк»"})

    by_name = await auth_client.get("/api/v1/crm/customers", params={"search": "ромашка"})
    by_phone = await auth_client.get("/api/v1/crm/customers", params={"search": "111-22"})
    missing = await auth_client.get("/api/v1/crm/customers", params={"search": "берёза"})

    assert [item["name"] for item in by_name.json()["items"]] == ["ООО «Ромашка»"]
    assert [item["name"] for item in by_phone.json()["items"]] == ["ООО «Ромашка»"]
    assert missing.json()["items"] == []
    assert missing.json()["total"] == 0


@pytest.mark.asyncio
async def test_every_copy_of_the_document_is_sealed_at_rest(
    auth_client, db_session: AsyncSession
):
    """The customer book was only one copy: versions and shared pages hold more."""
    from app.models.crm import CrmQuoteVersion
    from app.models.shared_quote import SharedQuote

    await subscription_service.set_paywall_enforced(db_session, False)

    created = await auth_client.post("/api/v1/crm/quotes", json=quote_payload())
    assert created.status_code == 201
    quote_id = created.json()["id"]

    shared = await auth_client.post(f"/api/v1/crm/quotes/{quote_id}/share")
    assert shared.status_code in (200, 201)

    version = (
        await db_session.execute(select(CrmQuoteVersion))
    ).scalars().first()
    assert isinstance(version.customer_snapshot, str)
    assert version.customer_snapshot.startswith("fh1:")
    assert isinstance(version.seller_snapshot, str)
    assert version.seller_snapshot.startswith("fh1:")
    assert version.html_content.startswith("fh1:")
    assert "Тестовая мастерская" not in version.html_content

    page = (await db_session.execute(select(SharedQuote))).scalars().first()
    if page is not None:
        assert page.html_content.startswith("fh1:")

    readable = await auth_client.get(f"/api/v1/crm/quotes/{quote_id}")
    assert readable.status_code == 200
