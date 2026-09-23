"""Regression tests for the verified administrative email inbox."""

import base64
import smtplib
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import email_communications
from app.core.config import settings
from app.models.brand import Brand
from app.models.brand_invite import BrandInvite
from app.models.email_communication import EmailMessage, EmailSendReservation, EmailThread
from app.services import email_service, inbound_mail_service
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
        internet_message_id="<durable-admin-message@filamenthub.test>",
    )

    message = delivered["message"]
    assert result.sent is True
    assert result.provider_message_id is None
    assert message["Message-ID"] == "<durable-admin-message@filamenthub.test>"
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
    assert result.acceptance_uncertain is False


def test_lost_smtp_response_is_reported_as_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)

    class LostResponseSMTP:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def starttls(self, *, context) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, message: object) -> None:
            raise TimeoutError("relay response was lost")

        def quit(self) -> None:
            pass

    monkeypatch.setattr(email_service.smtplib, "SMTP", LostResponseSMTP)
    result = email_service.send_email_tracked(
        to="recipient@example.com",
        subject="Unknown acceptance",
        html="<p>Hello</p>",
        internet_message_id="<lost-response@filamenthub.test>",
    )

    assert result.sent is False
    assert result.acceptance_uncertain is True
    assert result.provider_message_id is None


def test_pre_handoff_smtp_failure_is_reported_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-secret")

    def fail_before_handoff(message: object) -> None:
        raise ConnectionError("relay is unreachable")

    monkeypatch.setattr(email_service, "_deliver", fail_before_handoff)
    result = email_service.send_email_tracked(
        to="recipient@example.com",
        subject="Known failure",
        html="<p>Hello</p>",
    )

    assert result.sent is False
    assert result.acceptance_uncertain is False


def test_explicit_smtp_rejection_is_reported_as_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)

    class RejectingSMTP:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def starttls(self, *, context) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, message: object) -> None:
            raise smtplib.SMTPRecipientsRefused(
                {"recipient@example.com": (550, b"rejected")}
            )

        def quit(self) -> None:
            pass

    monkeypatch.setattr(email_service.smtplib, "SMTP", RejectingSMTP)
    result = email_service.send_email_tracked(
        to="recipient@example.com",
        subject="Rejected",
        html="<p>Hello</p>",
    )

    assert result.sent is False
    assert result.acceptance_uncertain is False


def test_cleanup_failure_after_acceptance_does_not_change_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SMTP_USER", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    closed = False

    class AcceptedSMTP:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def starttls(self, *, context) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            pass

        def send_message(self, message: object) -> None:
            pass

        def quit(self) -> None:
            raise smtplib.SMTPServerDisconnected("QUIT response lost")

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(email_service.smtplib, "SMTP", AcceptedSMTP)
    result = email_service.send_email_tracked(
        to="recipient@example.com",
        subject="Accepted",
        html="<p>Hello</p>",
    )

    assert result.sent is True
    assert result.acceptance_uncertain is False
    assert closed is True


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
        return EmailSendResult(sent=True)

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
    assert captured["headers"]["References"] == "<incoming-thread@example.com>"
    await db_session.refresh(thread)
    assert thread.reply_token
    assert captured["reply_to"] == f"thread-{thread.reply_token}@reply.filamenthub.test"

    outbound = await db_session.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == "email.reply.test-reply-key-0001"
        )
    )
    assert outbound is not None and outbound.sent_by_id == admin_user.id
    assert outbound.provider_message_id is None
    assert outbound.internet_message_id == captured["internet_message_id"]
    await db_session.refresh(thread)
    assert thread.unread_count == 1


@pytest.mark.asyncio
async def test_mark_read_stops_at_the_message_visible_to_the_admin(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    thread = EmailThread(
        participant_email="reader@example.com",
        subject="Two arrivals",
        unread_count=2,
    )
    db_session.add(thread)
    await db_session.flush()
    first = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email=thread.participant_email,
        recipient_emails=["support@filamenthub.test"],
        subject=thread.subject,
        text_body="Visible when the thread was opened.",
        provider_message_id="read-watermark-first",
        attachment_metadata=[],
        delivery_status="received",
    )
    second = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email=thread.participant_email,
        recipient_emails=["support@filamenthub.test"],
        subject=thread.subject,
        text_body="Arrived after the visible snapshot.",
        provider_message_id="read-watermark-second",
        attachment_metadata=[],
        delivery_status="received",
    )
    db_session.add_all([first, second])
    await db_session.commit()
    await db_session.refresh(first)
    await db_session.refresh(second)

    response = await admin_client.post(
        f"/api/v1/admin/communications/email-threads/{thread.id}/read",
        json={"through_message_id": first.id},
    )

    assert response.status_code == 200
    assert response.json()["unread_count"] == 1
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.read_at is not None
    assert second.read_at is None


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
        return EmailSendResult(sent=True)

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
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == "email.create.test-create-key-0001"
        )
    )
    assert message is not None and message.sent_by_id == admin_user.id
    assert message.provider_message_id is None
    assert message.internet_message_id == captured["internet_message_id"]


@pytest.mark.asyncio
async def test_thread_reply_address_routes_inbound_to_existing_thread(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    await email_communications.ingest_inbound_email(
        db_session,
        email_communications.InboundEmailData(
            participant_email="contact@example.com",
            participant_name="Example Plastics",
            subject="Re: FilamentHub partnership",
            body="We are interested.",
            recipients=[f"thread-{reply_token}@reply.filamenthub.test"],
            created_at=datetime.now(),
            provider_message_id="<inbound@example.com>",
            provider_event_id="local:thread-route-1",
            internet_message_id="<inbound@example.com>",
            in_reply_to="<outbound@example.com>",
            attachment_metadata=[],
        ),
    )

    assert await db_session.scalar(select(func.count(EmailThread.id))) == 1
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 2


@pytest.mark.asyncio
async def test_duplicate_inbound_delivery_is_ignored_without_a_second_thread(
    db_session: AsyncSession,
) -> None:
    received_at = datetime.now()
    delivery = email_communications.InboundEmailData(
        participant_email="repeat@example.com",
        participant_name="Repeat Sender",
        subject="The same delivery",
        body="This must be stored once.",
        recipients=["support@filamenthub.test"],
        created_at=received_at,
        provider_message_id="repeat-provider-message",
        provider_event_id="local:repeat-delivery",
        internet_message_id="<repeat-provider-message@example.com>",
        in_reply_to=None,
        attachment_metadata=[],
    )

    await email_communications.ingest_inbound_email(db_session, delivery)
    await email_communications.ingest_inbound_email(db_session, delivery)

    assert await db_session.scalar(select(func.count(EmailThread.id))) == 1
    assert await db_session.scalar(select(func.count(EmailMessage.id))) == 1
    thread = await db_session.scalar(select(EmailThread))
    assert thread is not None
    assert thread.unread_count == 1


@pytest.mark.asyncio
async def test_admin_can_permanently_delete_email_thread(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    stored = tmp_path / "stored"
    stored.mkdir(parents=True, exist_ok=True)
    raw_message = stored / "delete-thread-raw.eml"
    raw_message.write_bytes(b"From: delete@example.com\r\n\r\nDelete me")
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
            provider_message_id="delete-thread-message",
            provider_event_id="local:delete-thread-raw",
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
    assert not raw_message.exists()


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
async def test_failed_admin_send_is_reserved_and_not_retried_with_the_same_key(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fail_send(**kwargs):
        nonlocal calls
        calls += 1
        return EmailSendResult(sent=False, error="relay unavailable")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fail_send)
    payload = {
        "to": "partner@example.com",
        "subject": "Reserved delivery",
        "body": "Only one SMTP attempt is allowed for this key.",
        "sender_profile": "support",
        "idempotency_key": "email.create.failed-reservation-0001",
    }

    first = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )
    replay = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )

    assert first.status_code == 502
    assert replay.status_code == 502
    assert calls == 1
    message = await db_session.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == payload["idempotency_key"]
        )
    )
    assert message is not None
    assert message.delivery_status == "failed"


@pytest.mark.asyncio
async def test_lost_admin_smtp_response_is_uncertain_and_not_retried(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    captured_message_id: str | None = None

    def lose_response(**kwargs):
        nonlocal calls, captured_message_id
        calls += 1
        captured_message_id = kwargs["internet_message_id"]
        return EmailSendResult(
            sent=False,
            error="relay response was lost",
            acceptance_uncertain=True,
        )

    monkeypatch.setattr(email_communications, "send_admin_reply_email", lose_response)
    payload = {
        "to": "partner@example.com",
        "subject": "Unknown acceptance",
        "body": "The relay response may be lost.",
        "sender_profile": "support",
        "idempotency_key": "email.create.lost-response-0001",
    }

    first = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )
    replay = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )

    assert first.status_code == 409
    assert replay.status_code == 409
    assert first.json()["detail"]["code"] == "ERR_EMAIL_DELIVERY_UNCERTAIN"
    assert replay.json()["detail"]["code"] == "ERR_EMAIL_DELIVERY_UNCERTAIN"
    assert calls == 1
    message = await db_session.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == payload["idempotency_key"]
        )
    )
    assert message is not None
    assert message.delivery_status == "uncertain"
    assert message.internet_message_id == captured_message_id
    assert message.provider_message_id is None


@pytest.mark.asyncio
async def test_stale_send_becomes_uncertain_and_replay_never_calls_smtp(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "email.create.uncertain-reservation-0001"
    payload = {
        "to": "partner@example.com",
        "subject": "Unknown relay acceptance",
        "body": "The SMTP response was lost.",
        "sender_profile": "support",
        "idempotency_key": key,
    }
    thread = EmailThread(
        participant_email=payload["to"],
        subject=payload["subject"],
        sender_profile="support",
        language="en",
    )
    db_session.add(thread)
    await db_session.flush()
    message = EmailMessage(
        thread_id=thread.id,
        direction="outbound",
        sender_email=email_service.get_email_sender("support"),
        recipient_emails=[payload["to"]],
        subject=payload["subject"],
        text_body=payload["body"],
        client_idempotency_key=key,
        internet_message_id="<uncertain-reservation@filamenthub.test>",
        attachment_metadata=[],
        delivery_status="sending",
        created_at=datetime.now() - timedelta(days=1),
    )
    db_session.add(message)
    db_session.add(EmailSendReservation(idempotency_key=key))
    await db_session.commit()

    calls = 0

    def fake_send(**kwargs):
        nonlocal calls
        calls += 1
        return EmailSendResult(sent=True)

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    replay = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )

    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "ERR_EMAIL_DELIVERY_UNCERTAIN"
    assert calls == 0
    await db_session.refresh(message)
    assert message.delivery_status == "uncertain"

    deleted = await admin_client.delete(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )
    replay_after_delete = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )
    assert deleted.status_code == 200
    assert replay_after_delete.status_code == 409
    assert replay_after_delete.json()["detail"]["code"] == "ERR_EMAIL_IDEMPOTENCY_CONFLICT"
    assert calls == 0
    assert await db_session.get(EmailSendReservation, key) is not None


@pytest.mark.asyncio
async def test_uncertain_message_blocks_a_new_reply_without_smtp(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = EmailThread(
        participant_email="uncertain-thread@example.com",
        subject="Unresolved delivery",
        sender_profile="support",
        language="en",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        EmailMessage(
            thread_id=thread.id,
            direction="outbound",
            sender_email=email_service.get_email_sender("support"),
            recipient_emails=[thread.participant_email],
            subject=thread.subject,
            text_body="Acceptance is unknown.",
            client_idempotency_key="email.reply.uncertain-existing-0001",
            internet_message_id="<uncertain-thread@filamenthub.test>",
            attachment_metadata=[],
            delivery_status="uncertain",
        )
    )
    await db_session.commit()
    send_called = False

    def fake_send(**kwargs):
        nonlocal send_called
        send_called = True
        return EmailSendResult(sent=True)

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    response = await admin_client.post(
        f"/api/v1/admin/communications/email-threads/{thread.id}/reply",
        json={
            "body": "A second attempt must be blocked.",
            "idempotency_key": "email.reply.uncertain-new-0001",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_EMAIL_DELIVERY_UNCERTAIN"
    assert send_called is False


@pytest.mark.asyncio
async def test_reusing_email_key_for_different_content_is_rejected(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_send(**kwargs):
        nonlocal calls
        calls += 1
        return EmailSendResult(sent=True, provider_message_id="one-message-only")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    payload = {
        "to": "partner@example.com",
        "subject": "Stable payload",
        "body": "First body",
        "sender_profile": "support",
        "idempotency_key": "email.create.payload-conflict-0001",
    }
    first = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )
    changed = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        json={**payload, "body": "Different body"},
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "ERR_EMAIL_IDEMPOTENCY_CONFLICT"
    assert calls == 1


@pytest.mark.asyncio
async def test_reusing_email_key_for_different_attachment_bytes_is_rejected(
    admin_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_send(**kwargs):
        nonlocal calls
        calls += 1
        return EmailSendResult(sent=True, provider_message_id="one-attachment-only")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    data = {
        "to": "partner@example.com",
        "subject": "Stable attachment payload",
        "body": "The attachment bytes are part of the payload.",
        "sender_profile": "support",
        "idempotency_key": "email.create.attachment-conflict-0001",
    }
    first = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data=data,
        files=[("attachments", ("note.pdf", b"%PDF-A", "application/pdf"))],
    )
    changed = await admin_client.post(
        "/api/v1/admin/communications/email-threads",
        data=data,
        files=[("attachments", ("note.pdf", b"%PDF-B", "application/pdf"))],
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["detail"]["code"] == "ERR_EMAIL_IDEMPOTENCY_CONFLICT"
    assert calls == 1


@pytest.mark.asyncio
async def test_deleted_thread_keeps_outbound_send_key_reserved(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_send(**kwargs):
        nonlocal calls
        calls += 1
        return EmailSendResult(sent=True, provider_message_id="deleted-thread-send")

    monkeypatch.setattr(email_communications, "send_admin_reply_email", fake_send)
    payload = {
        "to": "partner@example.com",
        "subject": "Durable reservation",
        "body": "Deleting the conversation must not permit a second SMTP call.",
        "sender_profile": "support",
        "idempotency_key": "email.create.deleted-thread-key-0001",
    }
    created = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )
    deleted = await admin_client.delete(
        f"/api/v1/admin/communications/email-threads/{created.json()['id']}"
    )
    replay = await admin_client.post(
        "/api/v1/admin/communications/email-threads", json=payload
    )

    assert created.status_code == 201
    assert deleted.status_code == 200
    assert replay.status_code == 409
    assert calls == 1
    assert await db_session.get(
        EmailSendReservation, payload["idempotency_key"]
    ) is not None


@pytest.mark.asyncio
async def test_thread_cannot_be_deleted_while_smtp_attempt_is_active(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    thread = EmailThread(
        participant_email="active-send@example.com",
        subject="Active SMTP call",
    )
    db_session.add(thread)
    await db_session.flush()
    db_session.add(
        EmailMessage(
            thread_id=thread.id,
            direction="outbound",
            sender_email="FilamentHub <support@filamenthub.ru>",
            recipient_emails=[thread.participant_email],
            subject=thread.subject,
            text_body="Still sending",
            client_idempotency_key="email.create.active-delete-0001",
            attachment_metadata=[],
            delivery_status="sending",
        )
    )
    db_session.add(
        EmailSendReservation(idempotency_key="email.create.active-delete-0001")
    )
    await db_session.commit()

    response = await admin_client.delete(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_EMAIL_DELIVERY_IN_PROGRESS"
    assert await db_session.get(EmailThread, thread.id) is not None


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
        provider_message_id="<received-with-attachment-1@example.com>",
        provider_event_id="local:received-with-attachment-1",
        attachment_metadata=[
            {
                "filename": "price list.pdf",
                "content_type": "application/pdf",
                "size": 12,
                "provider_attachment_id": None,
            }
        ],
        delivery_status="received",
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    monkeypatch.setattr(
        inbound_mail_service,
        "read_stored_attachment",
        lambda event_id, index: (b"%PDF-content", "application/pdf", "price list.pdf"),
    )

    detail = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
    )
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["attachment_metadata"][0]["downloadable"] is True

    response = await admin_client.get(
        f"/api/v1/admin/communications/email-threads/{thread.id}"
        f"/messages/{message.id}/attachments/0"
    )

    assert response.status_code == 200
    assert response.content == b"%PDF-content"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert "price%20list.pdf" in response.headers["content-disposition"]

    preview_url = (
        f"/api/v1/admin/communications/email-threads/{thread.id}"
        f"/messages/{message.id}/attachments/0?preview=true"
    )
    assert (await admin_client.get(preview_url)).status_code == 404
    from io import BytesIO

    from PIL import Image

    source = BytesIO()
    Image.new("RGB", (32, 24), "red").save(source, format="TIFF")
    monkeypatch.setattr(
        inbound_mail_service,
        "read_stored_attachment",
        lambda event_id, index: (source.getvalue(), "image/tiff", "scan.tiff"),
    )
    preview = await admin_client.get(preview_url)
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["cache-control"] == "private, no-store"
    with Image.open(BytesIO(preview.content)) as image:
        assert image.size == (32, 24)



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
