"""Regression tests for the verified administrative email inbox."""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import email_communications
from app.core.config import settings
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.email_communication import EmailMessage, EmailThread
from app.services import email_service
from app.services.email_service import EmailSendResult


async def _invite(db: AsyncSession) -> BrandInvite:
    brand = Brand(name="Inbox Brand", slug="inbox-brand", active=True, verified=True)
    db.add(brand)
    await db.flush()
    invite = BrandInvite(
        token="invite-token-for-inbox",
        email="contact@inbox-brand.example",
        brand_name=brand.name,
        target_type="existing",
        brand_id=brand.id,
        sender_profile="pr",
        reply_token="A" * 32,
        invited_by_id=None,
        expires_at=datetime.now() + timedelta(days=14),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


def _webhook_headers(
    event_id: str,
    raw_body: bytes,
    *,
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp_value = str(timestamp if timestamp is not None else int(time.time()))
    signing_secret = base64.b64decode("dGVzdA==")
    signed_payload = f"{event_id}.{timestamp_value}.".encode() + raw_body
    signature = base64.b64encode(
        hmac.new(signing_secret, signed_payload, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": event_id,
        "svix-timestamp": timestamp_value,
        "svix-signature": f"v1,{signature}",
    }


def _webhook_payload() -> dict:
    return {
        "type": "email.received",
        "created_at": "2026-07-15T08:00:00Z",
        "data": {
            "email_id": "received-email-1",
            "from": "Brand Contact <contact@inbox-brand.example>",
            "to": [f"invite-{'A' * 32}@reply.filamenthub.test"],
            "message_id": "<incoming-message@example.com>",
            "subject": "Re: FilamentHub invitation",
        },
    }


@pytest.mark.asyncio
async def test_inbound_webhook_is_verified_sanitized_and_idempotent(
    client: AsyncClient,
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invite = await _invite(db_session)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_dGVzdA==")
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    monkeypatch.setattr(
        email_communications,
        "get_received_email",
        lambda email_id: {
            "id": email_id,
            "from": "Brand Contact <contact@inbox-brand.example>",
            "to": [f"invite-{'A' * 32}@reply.filamenthub.test"],
            "subject": "Re: FilamentHub invitation",
            "html": "<p>Hello <strong>FilamentHub</strong></p><script>alert(1)</script>",
            "text": None,
            "headers": {"in-reply-to": "<outgoing-message@example.com>"},
            "message_id": "<incoming-message@example.com>",
            "created_at": "2026-07-15T08:00:00Z",
            "attachments": [
                {
                    "filename": "../../price-list.pdf",
                    "content_type": "application/pdf",
                    "size": 321,
                }
            ],
        },
    )

    payload = _webhook_payload()
    raw_body = json.dumps(payload).encode()
    first = await client.post(
        "/api/v1/webhooks/resend",
        content=raw_body,
        headers=_webhook_headers("event-1", raw_body),
    )
    second = await client.post(
        "/api/v1/webhooks/resend",
        content=raw_body,
        headers=_webhook_headers("event-1", raw_body),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert await db_session.scalar(select(func.count(EmailThread.id))) == 1
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 1

    thread = await db_session.scalar(select(EmailThread))
    message = await db_session.scalar(select(EmailMessage))
    assert thread is not None and thread.invite_id == invite.id and thread.unread_count == 1
    assert message is not None
    assert message.text_body == "Hello FilamentHub"
    assert "alert" not in message.text_body
    assert message.attachment_metadata == [
        {"filename": "price-list.pdf", "content_type": "application/pdf", "size": 321}
    ]

    listed = await admin_client.get("/api/v1/admin/communications/email-threads")
    assert listed.status_code == 200
    assert listed.json()["unread_total"] == 1
    assert listed.json()["items"][0]["brand_name"] == "Inbox Brand"

    marked = await admin_client.post(
        f"/api/v1/admin/communications/email-threads/{thread.id}/read"
    )
    assert marked.status_code == 200
    assert marked.json()["unread_count"] == 0
    assert marked.json()["messages"][0]["read_at"] is not None


@pytest.mark.asyncio
async def test_invalid_webhook_signature_is_rejected(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_dGVzdA==")
    raw_body = json.dumps(_webhook_payload()).encode()
    headers = _webhook_headers("invalid-event", raw_body)
    headers["svix-signature"] = "v1,invalid"

    response = await client.post(
        "/api/v1/webhooks/resend",
        content=raw_body,
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_EMAIL_WEBHOOK_INVALID"


@pytest.mark.asyncio
async def test_stale_webhook_signature_is_rejected(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_dGVzdA==")
    raw_body = json.dumps(_webhook_payload()).encode()

    response = await client.post(
        "/api/v1/webhooks/resend",
        content=raw_body,
        headers=_webhook_headers("stale-event", raw_body, timestamp=int(time.time()) - 301),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_EMAIL_WEBHOOK_INVALID"


def test_received_email_uses_compatible_resend_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "received-email-1", "text": "Hello"}

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(email_service.httpx, "get", fake_get)

    result = email_service.get_received_email("received-email-1")

    assert result == {"id": "received-email-1", "text": "Hello"}
    assert captured["url"] == (
        "https://api.resend.com/emails/receiving/received-email-1"
    )
    assert captured["headers"] == {"Authorization": "Bearer re_test"}
    assert captured["params"] == {"html_format": "cid"}


@pytest.mark.asyncio
async def test_admin_reply_preserves_thread_headers_and_sender(
    admin_client: AsyncClient,
    admin_user,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invite = await _invite(db_session)
    thread = EmailThread(
        invite_id=invite.id,
        brand_id=invite.brand_id,
        participant_email="contact@inbox-brand.example",
        participant_name="Brand Contact",
        subject="Re: FilamentHub invitation",
        unread_count=1,
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        EmailMessage(
            thread_id=thread.id,
            direction="inbound",
            sender_email=thread.participant_email,
            recipient_emails=["invite@example.test"],
            subject=thread.subject,
            text_body="We are interested.",
            provider_message_id="received-email-reply",
            provider_event_id="event-reply",
            internet_message_id="<incoming-thread@example.com>",
            attachment_metadata=[],
        )
    )
    await db_session.commit()
    await db_session.refresh(thread)
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    captured: dict = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return EmailSendResult(sent=True, provider_message_id="sent-reply-1")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)

    response = await admin_client.post(
        f"/api/v1/admin/communications/email-threads/{thread.id}/reply",
        json={"body": "Thank you. We will help you onboard.", "sender_profile": "pr"},
    )
    assert response.status_code == 200
    assert response.json()["direction"] == "outbound"
    assert response.json()["delivery_status"] == "sent"
    assert captured["sender_profile"] == "pr"
    assert captured["headers"]["In-Reply-To"] == "<incoming-thread@example.com>"
    await db_session.refresh(thread)
    assert thread.reply_token
    assert captured["reply_to"] == f"thread-{thread.reply_token}@reply.filamenthub.test"

    outbound = await db_session.scalar(
        select(EmailMessage).where(EmailMessage.provider_message_id == "sent-reply-1")
    )
    assert outbound is not None and outbound.sent_by_id == admin_user.id


@pytest.mark.asyncio
async def test_admin_can_start_email_thread(
    admin_client: AsyncClient,
    admin_user,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    monkeypatch.setattr(settings, "EMAIL_CONTACT", "support@filamenthub.test")
    captured: dict = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return EmailSendResult(sent=True, provider_message_id="sent-new-thread-1")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)

    response = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        json={
            "to": "Contact@Example.com",
            "participant_name": "Example Plastics",
            "subject": "FilamentHub partnership",
            "body": "Hello from FilamentHub.",
            "sender_profile": "support",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["participant_email"] == "contact@example.com"
    assert payload["suggested_sender_profile"] == "support"
    assert payload["messages"][0]["delivery_status"] == "sent"
    assert captured["sender_profile"] == "support"
    assert captured["reply_to"].startswith("thread-")
    assert captured["reply_to"].endswith("@reply.filamenthub.test")

    thread = await db_session.get(EmailThread, payload["id"])
    assert thread is not None
    assert thread.sender_profile == "support"
    assert thread.reply_token
    message = await db_session.scalar(
        select(EmailMessage).where(EmailMessage.provider_message_id == "sent-new-thread-1")
    )
    assert message is not None and message.sent_by_id == admin_user.id


@pytest.mark.asyncio
async def test_thread_reply_address_routes_inbound_to_existing_thread(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_dGVzdA==")
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    reply_token = "B" * 32
    thread = EmailThread(
        participant_email="contact@example.com",
        participant_name="Example Plastics",
        subject="FilamentHub partnership",
        reply_token=reply_token,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        EmailMessage(
            thread_id=thread.id,
            direction="outbound",
            sender_email="FilamentHub <support@filamenthub.test>",
            recipient_emails=[thread.participant_email],
            subject=thread.subject,
            text_body="Hello from FilamentHub.",
            provider_message_id="sent-thread-route-1",
            attachment_metadata=[],
            delivery_status="sent",
        )
    )
    await db_session.commit()

    monkeypatch.setattr(
        email_communications,
        "get_received_email",
        lambda email_id: {
            "id": email_id,
            "from": "Example Plastics <contact@example.com>",
            "to": [f"thread-{reply_token}@reply.filamenthub.test"],
            "subject": "Re: FilamentHub partnership",
            "text": "We are interested.",
            "headers": {"in-reply-to": "<outbound@example.com>"},
            "message_id": "<inbound@example.com>",
            "created_at": "2026-07-15T10:00:00Z",
            "attachments": [],
        },
    )
    payload = {
        "type": "email.received",
        "data": {
            "email_id": "received-thread-route-1",
            "from": "contact@example.com",
            "to": [f"thread-{reply_token}@reply.filamenthub.test"],
            "subject": "Re: FilamentHub partnership",
        },
    }
    raw_body = json.dumps(payload).encode()
    response = await client.post(
        "/api/v1/webhooks/resend",
        content=raw_body,
        headers=_webhook_headers("event-thread-route-1", raw_body),
    )

    assert response.status_code == 200
    assert await db_session.scalar(select(func.count(EmailThread.id))) == 1
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 2


@pytest.mark.asyncio
async def test_delivery_webhook_updates_outbound_status_without_downgrade(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "RESEND_WEBHOOK_SECRET", "whsec_dGVzdA==")
    thread = EmailThread(
        participant_email="contact@example.com",
        subject="Delivery status",
        reply_token="C" * 32,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    message = EmailMessage(
        thread_id=thread.id,
        direction="outbound",
        sender_email="FilamentHub <support@filamenthub.test>",
        recipient_emails=[thread.participant_email],
        subject=thread.subject,
        text_body="Delivery test",
        provider_message_id="sent-delivery-status-1",
        attachment_metadata=[],
        delivery_status="sent",
    )
    db_session.add(message)
    await db_session.commit()

    async def post_event(event_id: str, event_type: str) -> None:
        payload = {
            "type": event_type,
            "data": {"email_id": "sent-delivery-status-1"},
        }
        raw_body = json.dumps(payload).encode()
        response = await client.post(
            "/api/v1/webhooks/resend",
            content=raw_body,
            headers=_webhook_headers(event_id, raw_body),
        )
        assert response.status_code == 200

    await post_event("event-delivered-1", "email.delivered")
    await db_session.refresh(message)
    assert message.delivery_status == "delivered"

    await post_event("event-sent-late-1", "email.sent")
    await db_session.refresh(message)
    assert message.delivery_status == "delivered"


@pytest.mark.asyncio
async def test_admin_can_permanently_delete_email_thread(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    thread = EmailThread(
        participant_email="delete@example.com",
        subject="Delete this thread",
        reply_token="D" * 32,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        EmailMessage(
            thread_id=thread.id,
            direction="inbound",
            sender_email=thread.participant_email,
            recipient_emails=["support@filamenthub.test"],
            subject=thread.subject,
            text_body="This thread should be deleted.",
            attachment_metadata=[],
            delivery_status="received",
        )
    )
    await db_session.commit()

    response = await admin_client.delete(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert await db_session.scalar(select(func.count(EmailThread.id))) == 0
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 0
