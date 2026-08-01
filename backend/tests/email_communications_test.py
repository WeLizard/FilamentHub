"""Regression tests for the verified administrative email inbox."""

import base64
import hashlib
import hmac
import json
import time
from contextlib import nullcontext
from datetime import datetime, timedelta

import httpx
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
from app.services.email_service import EmailSendResult, ReceivedEmailAttachment


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
                    "id": "attachment-1",
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
        {
            "filename": "price-list.pdf",
            "content_type": "application/pdf",
            "size": 321,
            "provider_attachment_id": "attachment-1",
            "content_id": None,
            "inline": False,
            "content_id_checked": True,
        }
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


def test_tracked_email_is_handed_to_the_relay_as_mime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-secret")
    delivered: dict[str, object] = {}

    def fake_deliver(message: object) -> None:
        delivered["message"] = message

    monkeypatch.setattr(email_service, "_deliver", fake_deliver)
    result = email_service.send_email_tracked(
        to='"Brand" <recipient@example.com>',
        subject="Threaded reply",
        html="<p>Hello</p>",
        text="Hello",
        sender_profile="support",
        reply_to="thread-token@reply.filamenthub.ru",
        headers={"In-Reply-To": "<inbound-1@example.com>"},
        attachments=[
            {"filename": "note.txt", "content": "SGVsbG8=", "content_type": "text/plain"}
        ],
        idempotency_key="email.create.http-header-0001",
    )

    message = delivered["message"]
    assert result.sent is True
    assert result.provider_message_id == message["Message-ID"].strip("<>")
    assert message["Subject"] == "Threaded reply"
    assert message["Reply-To"] == "thread-token@reply.filamenthub.ru"
    assert message["In-Reply-To"] == "<inbound-1@example.com>"
    assert settings.EMAIL_CONTACT in message["From"]

    parts = {part.get_content_type() for part in message.walk()}
    assert {"text/plain", "text/html"} <= parts
    attachments = [part for part in message.walk() if part.get_filename()]
    assert [part.get_filename() for part in attachments] == ["note.txt"]
    assert attachments[0].get_content_type() == "text/plain"


def test_outgoing_mail_stops_when_smtp_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")

    def explode(message: object) -> None:
        raise AssertionError("delivery must not be attempted without credentials")

    monkeypatch.setattr(email_service, "_deliver", explode)
    result = email_service.send_email_tracked(
        to="recipient@example.com", subject="No relay", html="<p>Hello</p>"
    )

    assert result.sent is False
    assert "SMTP" in (result.error or "")


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
        json={
            "body": "Thank you. We will help you onboard.",
            "sender_profile": "pr",
            "idempotency_key": "email.reply.test-reply-key-0001",
        },
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
            "idempotency_key": "email.create.test-create-key-0001",
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


@pytest.mark.asyncio
async def test_multipart_compose_sanitizes_html_sends_attachment_and_replays(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    captured_calls: list[dict] = []

    def fake_send(**kwargs):
        captured_calls.append(kwargs)
        return EmailSendResult(sent=True, provider_message_id="sent-rich-compose-1")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    data = {
        "to": "partner@example.com",
        "participant_name": "Partner",
        "subject": "Rich attachment",
        "body": "Hello partner",
        "html_body": "<p>Hello <strong>partner</strong></p><script>alert(1)</script>",
        "sender_profile": "partnerships",
        "idempotency_key": "email.create.multipart-rich-0001",
    }
    files = [
        (
            "attachments",
            ("guide.pdf", b"%PDF-1.4\nFilamentHub\n%%EOF", "application/pdf"),
        )
    ]

    first = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data=data,
        files=files,
    )
    replay = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data=data,
        files=files,
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert len(captured_calls) == 1
    assert captured_calls[0]["sender_profile"] == "partnerships"
    assert captured_calls[0]["idempotency_key"] == data["idempotency_key"]
    assert captured_calls[0]["attachments"][0]["filename"] == "guide.pdf"
    assert "script" not in captured_calls[0]["html_body"]
    payload = first.json()
    assert payload["messages"][0]["html_body"] == "<p>Hello <strong>partner</strong></p>"
    assert payload["messages"][0]["attachment_metadata"] == [
        {
            "index": 0,
            "filename": "guide.pdf",
            "content_type": "application/pdf",
            "size": 26,
            "downloadable": False,
            "content_id": None,
            "inline": False,
        }
    ]
    assert await db_session.scalar(select(func.count(EmailThread.id))) == 1
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 1


@pytest.mark.asyncio
async def test_multipart_compose_rejects_extension_content_mismatch(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    send_called = False

    def fake_send(**kwargs):
        nonlocal send_called
        send_called = True
        return EmailSendResult(sent=True, provider_message_id="should-not-send")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    response = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data={
            "to": "partner@example.com",
            "subject": "Bad attachment",
            "body": "Please see attachment",
            "sender_profile": "support",
            "idempotency_key": "email.create.bad-attachment-0001",
        },
        files=[
            (
                "attachments",
                ("not-a-pdf.pdf", b"MZ executable content", "application/pdf"),
            )
        ],
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_EMAIL_ATTACHMENT_TYPE"
    assert send_called is False


@pytest.mark.asyncio
async def test_admin_downloads_inbound_attachment_through_backend(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = EmailThread(
        participant_email="sender@example.com",
        subject="Attachment",
        reply_token="E" * 32,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    message = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email="sender@example.com",
        recipient_emails=["support@filamenthub.test"],
        subject=thread.subject,
        text_body="Attached.",
        provider_message_id="received-with-attachment-1",
        attachment_metadata=[
            {
                "filename": "price list.pdf",
                "content_type": "application/pdf",
                "size": 12,
                "provider_attachment_id": "attachment-download-1",
            }
        ],
        delivery_status="received",
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    monkeypatch.setattr(
        email_communications,
        "get_received_email_attachment",
        lambda email_id, attachment_id: ReceivedEmailAttachment(
            content=b"%PDF-content",
            content_type="application/pdf",
        ),
    )

    response = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
        f"/messages/{message.id}/attachments/0"
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-content"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert "price%20list.pdf" in response.headers["content-disposition"]


def test_received_attachment_downloads_from_current_resend_cdn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_response = httpx.Response(
        200,
        json={
            "content_type": "application/octet-stream",
            "download_url": "https://cdn.resend.app/email-1/attachments/image-1?signature=x",
        },
        request=httpx.Request("GET", "https://api.resend.com"),
    )
    download_response = httpx.Response(
        200,
        content=b"\x89PNG\r\n\x1a\ncontent",
        headers={"content-type": "application/octet-stream"},
        request=httpx.Request("GET", "https://cdn.resend.app"),
    )
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service.httpx, "get", lambda *args, **kwargs: metadata_response)
    monkeypatch.setattr(
        email_service.httpx,
        "stream",
        lambda *args, **kwargs: nullcontext(download_response),
    )

    attachment = email_service.get_received_email_attachment("email-1", "image-1")

    assert attachment.content == b"\x89PNG\r\n\x1a\ncontent"
    assert attachment.content_type == "image/png"


def test_received_attachment_rejects_lookalike_resend_cdn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_response = httpx.Response(
        200,
        json={"download_url": "https://cdn.resend.app.attacker.example/image-1"},
        request=httpx.Request("GET", "https://api.resend.com"),
    )
    stream_called = False

    def _unexpected_stream(*args: object, **kwargs: object) -> None:
        nonlocal stream_called
        stream_called = True

    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_service.httpx, "get", lambda *args, **kwargs: metadata_response)
    monkeypatch.setattr(email_service.httpx, "stream", _unexpected_stream)

    with pytest.raises(RuntimeError, match="Unexpected Resend attachment download URL"):
        email_service.get_received_email_attachment("email-1", "image-1")

    assert stream_called is False


def test_inline_image_keeps_the_name_the_letter_calls_it_by() -> None:
    stored = email_communications._attachment_metadata(
        [
            {
                "id": "attachment-inline-1",
                "filename": "signature.png",
                "content_type": "image/png",
                "content_disposition": "inline",
                "content_id": "<img001>",
            },
            {
                "id": "attachment-plain-1",
                "filename": "offer.pdf",
                "content_type": "application/pdf",
                "content_disposition": "attachment",
            },
        ]
    )

    assert stored[0]["content_id"] == "img001"
    assert stored[0]["inline"] is True
    assert stored[1]["content_id"] is None
    assert stored[1]["inline"] is False


@pytest.mark.asyncio
async def test_letter_stored_before_we_kept_content_id_asks_the_provider_once(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The image in an old letter is only a hole until the identifier comes back."""
    thread = EmailThread(
        participant_email="sender@example.com",
        subject="Inline image",
        reply_token="F" * 32,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    message = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email="sender@example.com",
        recipient_emails=["support@filamenthub.test"],
        subject=thread.subject,
        text_body="See the picture.",
        html_body='<p>See</p><img src="cid:img001">',
        provider_message_id="received-inline-1",
        attachment_metadata=[
            {
                "filename": "signature.png",
                "content_type": "image/png",
                "size": 12,
                "provider_attachment_id": "attachment-inline-1",
            }
        ],
        delivery_status="received",
    )
    db_session.add(message)
    await db_session.commit()

    provider_calls: list[str] = []

    def _fetch(email_id: str) -> dict:
        provider_calls.append(email_id)
        return {
            "attachments": [
                {
                    "id": "attachment-inline-1",
                    "filename": "signature.png",
                    "content_type": "image/png",
                    "content_disposition": "inline",
                    "content_id": "img001",
                    "size": 12,
                }
            ]
        }

    monkeypatch.setattr(email_communications, "get_received_email", _fetch)

    first = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )
    second = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )

    assert first.status_code == 200
    attachment = first.json()["messages"][0]["attachment_metadata"][0]
    assert attachment["content_id"] == "img001"
    assert attachment["inline"] is True
    assert attachment["downloadable"] is True
    assert second.json()["messages"][0]["attachment_metadata"][0]["content_id"] == "img001"
    assert provider_calls == ["received-inline-1"]


@pytest.mark.asyncio
async def test_provider_answer_without_the_files_keeps_what_we_stored(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the filenames over a missing image would be the worse trade."""
    thread = EmailThread(
        participant_email="sender@example.com",
        subject="Inline image gone",
        reply_token="G" * 32,
        sender_profile="support",
    )
    db_session.add(thread)
    await db_session.flush()
    message = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email="sender@example.com",
        recipient_emails=["support@filamenthub.test"],
        subject=thread.subject,
        text_body="See the picture.",
        html_body='<img src="cid:img001">',
        provider_message_id="received-inline-2",
        attachment_metadata=[
            {
                "filename": "signature.png",
                "content_type": "image/png",
                "size": 12,
                "provider_attachment_id": "attachment-inline-1",
            }
        ],
        delivery_status="received",
    )
    db_session.add(message)
    await db_session.commit()

    provider_calls: list[str] = []

    def _fetch(email_id: str) -> dict:
        provider_calls.append(email_id)
        return {"attachments": []}

    monkeypatch.setattr(email_communications, "get_received_email", _fetch)

    first = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )
    second = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )

    assert first.json()["messages"][0]["attachment_metadata"][0]["filename"] == "signature.png"
    assert second.json()["messages"][0]["attachment_metadata"][0]["filename"] == "signature.png"
    assert provider_calls == ["received-inline-2"]


@pytest.mark.asyncio
async def test_a_web_page_reaches_the_provider_and_the_recipient_is_named(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole trip: a chosen .html file has to arrive at the provider intact."""
    monkeypatch.setattr(settings, "EMAIL_INBOUND_DOMAIN", "reply.filamenthub.test")
    captured_calls: list[dict] = []

    def fake_send(**kwargs):
        captured_calls.append(kwargs)
        return EmailSendResult(sent=True, provider_message_id="sent-html-1")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    page = b"<!doctype html><html><body><h1>Partner application</h1></body></html>"
    response = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data={
            "to": "team@orcaslicer.example.com",
            "participant_name": "OrcaSlicer team",
            "subject": "Partner application",
            "body": "Please find our filled application attached.",
            "sender_profile": "partnerships",
            "idempotency_key": "email.create.html-attachment-0001",
        },
        files=[("attachments", ("application.html", page, "text/html"))],
    )

    assert response.status_code == 201, response.text
    assert captured_calls[0]["attachments"][0]["filename"] == "application.html"
    assert base64.b64decode(captured_calls[0]["attachments"][0]["content"]) == page
    assert captured_calls[0]["participant_name"] == "OrcaSlicer team"

    stored = response.json()["messages"][0]["attachment_metadata"]
    assert stored[0]["filename"] == "application.html"
    assert stored[0]["content_type"] == "text/html"
