"""Locally delivered mail must reach the administrative communication inbox."""

import os
import time
from email.message import EmailMessage

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email_communication import EmailMessage as StoredEmailMessage
from app.models.email_communication import EmailThread
from app.services import inbound_mail_service as inbound


def _letter(
    *,
    sender: str = "Brand Rep <rep@example.com>",
    to: str = "thread-abcdefghijklmnopqrst@filamenthub.ru",
    subject: str = "Re: приглашение",
    text: str = "Здравствуйте, нам интересно.",
    html: str | None = None,
    attachment: tuple[str, bytes, str] | None = None,
) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = "<inbound-1@example.com>"
    message["Date"] = "Sat, 01 Aug 2026 12:00:00 +0000"
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    if attachment:
        filename, content, content_type = attachment
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


def test_letter_is_parsed_into_the_shape_ingestion_expects():
    data = inbound.parse_inbound_message(_letter(), "local:abc")

    assert data is not None
    assert data.participant_email == "rep@example.com"
    assert data.participant_name == "Brand Rep"
    assert data.subject == "Re: приглашение"
    assert "интересно" in data.body
    assert data.provider_event_id == "local:abc"
    assert data.internet_message_id == "<inbound-1@example.com>"
    assert any("thread-abcdefghijklmnopqrst@filamenthub.ru" in item for item in data.recipients)
    assert data.created_at.tzinfo is not None


def test_envelope_recipient_is_seen_even_when_it_is_not_in_the_to_header():
    raw = _letter(to="someone-else@example.com")
    with_envelope = b"X-Original-To: thread-abcdefghijklmnopqrst@filamenthub.ru\r\n" + raw

    data = inbound.parse_inbound_message(with_envelope, "local:abc")

    assert data is not None
    assert any("thread-abcdefghijklmnopqrst" in item for item in data.recipients)


def test_html_only_letter_still_produces_readable_text():
    message = EmailMessage()
    message["From"] = "rep@example.com"
    message["To"] = "support@filamenthub.ru"
    message["Subject"] = "HTML only"
    message.set_content("<p>Первая строка</p><p>Вторая</p>", subtype="html")

    data = inbound.parse_inbound_message(message.as_bytes(), "local:html")

    assert data is not None
    assert "Первая строка" in data.body
    assert "<p>" not in data.body


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not a mail at all",
        b"From: \r\nSubject: no sender\r\n\r\nbody",
    ],
)
def test_unusable_letters_are_rejected_rather_than_raising(raw):
    assert inbound.parse_inbound_message(raw, "local:junk") is None


def test_attachment_is_listed_and_can_be_read_back(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    raw = _letter(attachment=("spec.txt", b"payload", "text/plain"))

    data = inbound.parse_inbound_message(raw, "local:withfile")
    assert data is not None
    names = [item["filename"] for item in data.attachment_metadata]
    assert "spec.txt" in names

    stored = tmp_path / "stored"
    stored.mkdir(parents=True, exist_ok=True)
    (stored / "withfile.eml").write_bytes(raw)

    index = names.index("spec.txt")
    result = inbound.read_stored_attachment("local:withfile", index)
    assert result is not None
    content, content_type, filename = result
    assert content == b"payload"
    assert content_type == "text/plain"
    assert filename == "spec.txt"


def test_stored_path_refuses_to_escape_its_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))

    assert inbound.stored_message_path("local:../../etc/passwd") is None
    assert inbound.stored_message_path("local:sub/dir") is None
    assert inbound.stored_message_path("external-event-id") is None


@pytest.mark.asyncio
async def test_a_broken_letter_is_quarantined_and_does_not_stop_the_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    incoming = tmp_path / "new"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "aaa.eml").write_bytes(b"not a mail at all")
    (incoming / "bbb.eml").write_bytes(_letter())

    ingested: list[str] = []

    async def fake_ingest(db, data):
        ingested.append(data.provider_event_id)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(inbound, "ingest_inbound_email", fake_ingest)
    accepted = await inbound.process_pending_mail(lambda: _Session())

    assert accepted == 1
    assert ingested == ["local:bbb"]
    assert (tmp_path / "failed" / "aaa.eml").is_file()
    assert (tmp_path / "stored" / "bbb.eml").is_file()
    assert not list(incoming.glob("*.eml"))


def test_only_one_worker_can_claim_the_same_message(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INBOUND_MAIL_CLAIM_TIMEOUT_SECONDS", 60)
    incoming, processing, _, _ = inbound._ensure_layout()
    source = incoming / "one.eml"
    source.write_bytes(_letter())
    old = time.time() - 120
    os.utime(source, (old, old))

    first = inbound._claim_pending(incoming, processing)
    second = inbound._claim_pending(incoming, processing)

    assert [path.name for path in first] == ["one.eml"]
    assert second == []
    assert inbound._recover_stale_claims(processing, incoming, time.time()) == 0
    assert (processing / "one.eml").is_file()


def test_abandoned_processing_claim_is_recovered(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INBOUND_MAIL_CLAIM_TIMEOUT_SECONDS", 60)
    incoming, processing, _, _ = inbound._ensure_layout()
    claimed = processing / "abandoned.eml"
    claimed.write_bytes(_letter())
    old = time.time() - 120
    os.utime(claimed, (old, old))

    recovered = inbound._recover_stale_claims(processing, incoming, time.time())

    assert recovered == 1
    assert (incoming / "abandoned.eml").is_file()
    assert not claimed.exists()


@pytest.mark.asyncio
async def test_maintenance_expires_raw_mail_and_marks_attachment_unavailable(
    tmp_path,
    monkeypatch,
    db_session: AsyncSession,
):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INBOUND_MAIL_STORED_RETENTION_DAYS", 1)
    monkeypatch.setattr(settings, "INBOUND_MAIL_FAILED_RETENTION_DAYS", 1)
    monkeypatch.setattr(settings, "INBOUND_MAIL_MAX_STORAGE_BYTES", 1024 * 1024 * 1024)
    _, _, stored, failed = inbound._ensure_layout()

    thread = EmailThread(participant_email="sender@example.com", subject="Old mail")
    db_session.add(thread)
    await db_session.flush()
    message = StoredEmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email="sender@example.com",
        recipient_emails=["support@filamenthub.ru"],
        subject="Old mail",
        text_body="Old body",
        provider_message_id="old-provider-message",
        provider_event_id="local:old-stored",
        attachment_metadata=[{"filename": "old.txt"}],
        delivery_status="received",
    )
    db_session.add(message)
    await db_session.commit()
    message_id = message.id

    stored_file = stored / "old-stored.eml"
    failed_file = failed / "old-failed.eml"
    stored_file.write_bytes(_letter())
    failed_file.write_bytes(b"broken")
    old = time.time() - 2 * 24 * 60 * 60
    os.utime(stored_file, (old, old))
    os.utime(failed_file, (old, old))

    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    await inbound.maintain_mail_storage(lambda: _SessionContext())

    db_session.expire_all()
    persisted = await db_session.scalar(
        select(StoredEmailMessage).where(StoredEmailMessage.id == message_id)
    )
    assert persisted is not None
    assert persisted.provider_event_id is None
    assert not stored_file.exists()
    assert not failed_file.exists()


@pytest.mark.asyncio
async def test_maintenance_removes_unlinked_raw_mail_after_grace(
    tmp_path,
    monkeypatch,
    db_session: AsyncSession,
):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INBOUND_MAIL_ORPHAN_GRACE_SECONDS", 60)
    monkeypatch.setattr(settings, "INBOUND_MAIL_STORED_RETENTION_DAYS", 365)
    _, _, stored, _ = inbound._ensure_layout()
    orphan = stored / "orphaned-after-delete.eml"
    orphan.write_bytes(_letter())
    old = time.time() - 120
    os.utime(orphan, (old, old))

    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    await inbound.maintain_mail_storage(lambda: _SessionContext())

    assert not orphan.exists()


@pytest.mark.asyncio
async def test_mail_health_reports_when_pending_mail_alone_exceeds_quota(
    tmp_path,
    monkeypatch,
    db_session: AsyncSession,
):
    monkeypatch.setattr(settings, "INBOUND_MAIL_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "INBOUND_MAIL_MAX_STORAGE_BYTES", 1)
    incoming, _, _, _ = inbound._ensure_layout()
    (incoming / "pending.eml").write_bytes(b"x" * (20 * 1024 * 1024 + 1))

    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    await inbound.maintain_mail_storage(lambda: _SessionContext())

    health = inbound.mail_storage_health()
    assert health["ready"] is True
    assert health["over_quota"] is True
    assert health["total_bytes"] > health["quota_bytes"]
    assert health["protected_bytes"] == health["total_bytes"]
