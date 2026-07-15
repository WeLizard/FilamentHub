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
    assert captured["sender_profile"] == "pr"
    assert captured["headers"]["In-Reply-To"] == "<incoming-thread@example.com>"
    assert captured["reply_to"] == f"invite-{'A' * 32}@reply.filamenthub.test"

    outbound = await db_session.scalar(
        select(EmailMessage).where(EmailMessage.provider_message_id == "sent-reply-1")
    )
    assert outbound is not None and outbound.sent_by_id == admin_user.id
