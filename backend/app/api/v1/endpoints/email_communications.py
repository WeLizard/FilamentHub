"""Verified Resend inbound webhook and the administrative communication inbox."""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser
from math import ceil
from typing import Annotated, Literal, TypeVar
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_EMAIL_ATTACHMENT_FETCH_FAILED,
    ERR_EMAIL_ATTACHMENT_NOT_FOUND,
    ERR_EMAIL_DELIVERY_FAILED,
    ERR_EMAIL_IDEMPOTENCY_CONFLICT,
    ERR_EMAIL_INBOUND_FETCH_FAILED,
    ERR_EMAIL_THREAD_NOT_FOUND,
    ERR_EMAIL_WEBHOOK_INVALID,
    ERR_EMAIL_WEBHOOK_NOT_CONFIGURED,
    raise_error,
)
from app.core.i18n import DEFAULT_LANGUAGE
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.brand_invite import BrandInvite
from app.models.email_communication import EmailMessage, EmailThread
from app.models.user import User
from app.schemas.email_communication import (
    EmailMessageResponse,
    EmailThreadCreate,
    EmailThreadDetailResponse,
    EmailThreadListResponse,
    EmailThreadReplyCreate,
    EmailThreadStatusUpdate,
    EmailThreadSummaryResponse,
)
from app.services.email_attachment_service import prepare_email_attachments
from app.services.email_service import (
    get_email_sender,
    get_received_email,
    get_received_email_attachment,
    sanitize_admin_email_html,
    send_admin_reply_email,
)

logger = logging.getLogger(__name__)

webhook_router = APIRouter(prefix="/webhooks/resend", tags=["webhooks"])
admin_router = APIRouter(prefix="/admin/communications", tags=["admin"])

_MAX_WEBHOOK_BYTES = 256 * 1024
_MAX_BODY_CHARS = 100_000
_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS = 5 * 60
_REPLY_TOKEN_PATTERN = re.compile(r"^invite-([A-Za-z0-9_-]{20,64})$")
_THREAD_TOKEN_PATTERN = re.compile(r"^thread-([A-Za-z0-9_-]{20,64})$")
_RESEND_ATTACHMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CONTENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._@%+-]{1,190}$")
_CID_REFERENCE_PATTERN = re.compile(r"cid:", re.IGNORECASE)
_MAX_BACKFILLED_MESSAGES_PER_THREAD = 5
_MANUAL_SENDER_PROFILES = {"support", "partnerships", "pr"}
_DELIVERY_EVENT_STATUSES = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
}
_DELIVERY_STATUS_RANK = {"sent": 1, "delayed": 2, "delivered": 3}
_EmailPayload = TypeVar("_EmailPayload", bound=BaseModel)


class _PlainTextParser(HTMLParser):
    """Convert untrusted email HTML to display-only plain text."""

    _BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    _IGNORED_TAGS = {"script", "style", "svg", "template", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in self._IGNORED_TAGS:
            self.ignored_depth += 1
        elif not self.ignored_depth and normalized in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self._IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and normalized in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line).strip()


def _truncate(value: object, limit: int) -> str:
    return str(value or "").replace("\x00", "").strip()[:limit]


def _header_value(value: object, limit: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def _verify_svix_signature(
    *,
    raw_body: bytes,
    event_id: str,
    timestamp: str,
    signature: str,
    secret: str,
) -> None:
    """Verify a Resend/Svix signature without requiring a newer Resend SDK."""
    if (
        not secret.startswith("whsec_")
        or len(event_id) > 200
        or len(timestamp) > 20
        or len(signature) > 2048
    ):
        raise ValueError("Invalid webhook signature metadata")

    try:
        timestamp_value = int(timestamp)
    except ValueError as exc:
        raise ValueError("Invalid webhook timestamp") from exc
    if abs(int(time.time()) - timestamp_value) > _WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError("Webhook timestamp is outside the accepted window")

    encoded_secret = secret.removeprefix("whsec_")
    encoded_secret += "=" * (-len(encoded_secret) % 4)
    try:
        secret_bytes = base64.b64decode(
            encoded_secret,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid webhook signing secret") from exc
    if not secret_bytes:
        raise ValueError("Invalid webhook signing secret")

    signed_payload = f"{event_id}.{timestamp}.".encode() + raw_body
    expected_signature = base64.b64encode(
        hmac.new(secret_bytes, signed_payload, hashlib.sha256).digest()
    ).decode()
    valid = False
    for candidate in signature.split():
        version, separator, value = candidate.partition(",")
        if separator and version == "v1" and hmac.compare_digest(value, expected_signature):
            valid = True
            break
    if not valid:
        raise ValueError("Invalid webhook signature")


def _string_list(value: object, *, limit: int = 50) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_truncate(item, 500) for item in value[:limit] if _truncate(item, 500)]


def _plain_text(text: object, html: object) -> str:
    normalized = _truncate(text, _MAX_BODY_CHARS)
    if normalized:
        return normalized
    if not html:
        return ""
    parser = _PlainTextParser()
    try:
        parser.feed(str(html)[:_MAX_BODY_CHARS * 2])
        parser.close()
    except Exception:
        logger.warning("Failed to convert inbound email HTML to text", exc_info=True)
        return ""
    return parser.text()[:_MAX_BODY_CHARS]


def _content_id(value: object) -> str | None:
    """Read the identifier an inline image is referenced by inside the letter."""
    raw = _header_value(value, 190).strip().lstrip("<").rstrip(">")
    return raw if _CONTENT_ID_PATTERN.fullmatch(raw) else None


def _attachment_metadata(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    attachments: list[dict] = []
    for item in value[:50]:
        if not isinstance(item, dict):
            continue
        raw_name = _header_value(item.get("filename"), 255).replace("\\", "/")
        filename = raw_name.rsplit("/", 1)[-1] or "attachment"
        size = item.get("size")
        provider_attachment_id = _header_value(item.get("id"), 128)
        attachments.append(
            {
                "filename": filename,
                "content_type": _truncate(item.get("content_type"), 100) or None,
                "size": size if isinstance(size, int) and size >= 0 else None,
                "provider_attachment_id": (
                    provider_attachment_id
                    if _RESEND_ATTACHMENT_ID_PATTERN.fullmatch(provider_attachment_id)
                    else None
                ),
                "content_id": _content_id(item.get("content_id")),
                "inline": _truncate(item.get("content_disposition"), 20).casefold() == "inline",
                "content_id_checked": True,
            }
        )
    return attachments


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _reply_token(recipients: list[str]) -> str | None:
    inbound_domain = settings.EMAIL_INBOUND_DOMAIN.strip().casefold().lstrip("@")
    if not inbound_domain:
        return None
    for recipient in recipients:
        _, address = parseaddr(recipient)
        local, separator, domain = address.rpartition("@")
        if not separator or domain.casefold().rstrip(".") != inbound_domain:
            continue
        match = _REPLY_TOKEN_PATTERN.fullmatch(local)
        if match:
            return match.group(1)
    return None


def _thread_token(recipients: list[str]) -> str | None:
    inbound_domain = settings.EMAIL_INBOUND_DOMAIN.strip().casefold().lstrip("@")
    if not inbound_domain:
        return None
    for recipient in recipients:
        _, address = parseaddr(recipient)
        local, separator, domain = address.rpartition("@")
        if not separator or domain.casefold().rstrip(".") != inbound_domain:
            continue
        match = _THREAD_TOKEN_PATTERN.fullmatch(local)
        if match:
            return match.group(1)
    return None


def _sender_profile_for_recipients(recipients: list[str]) -> str:
    recipient_addresses = {parseaddr(value)[1].casefold() for value in recipients}
    sender_addresses = {
        "support": settings.EMAIL_CONTACT,
        "partnerships": settings.EMAIL_PARTNERSHIPS_FROM,
        "pr": settings.EMAIL_PR_FROM,
    }
    for profile, address in sender_addresses.items():
        if address.strip().casefold() in recipient_addresses:
            return profile
    return "support"


def _ensure_thread_reply_token(thread: EmailThread) -> str:
    if not thread.reply_token:
        thread.reply_token = secrets.token_urlsafe(24)
    return thread.reply_token


def _thread_reply_address(thread: EmailThread) -> str:
    inbound_domain = settings.EMAIL_INBOUND_DOMAIN.strip().casefold().lstrip("@")
    if not inbound_domain:
        return settings.EMAIL_CONTACT
    return f"thread-{_ensure_thread_reply_token(thread)}@{inbound_domain}"


def _advance_delivery_status(current: str | None, incoming: str) -> str:
    if current in {"bounced", "complained"}:
        return current
    if incoming in {"bounced", "complained"}:
        return incoming
    if _DELIVERY_STATUS_RANK.get(incoming, 0) >= _DELIVERY_STATUS_RANK.get(current or "", 0):
        return incoming
    return current or incoming


def _message_response(message: EmailMessage) -> EmailMessageResponse:
    attachments = []
    for index, raw_attachment in enumerate(message.attachment_metadata):
        attachment = raw_attachment if isinstance(raw_attachment, dict) else {}
        attachments.append(
            {
                "index": index,
                "filename": str(attachment.get("filename") or "attachment"),
                "content_type": attachment.get("content_type"),
                "size": attachment.get("size"),
                "downloadable": bool(
                    message.direction == "inbound"
                    and message.provider_message_id
                    and attachment.get("provider_attachment_id")
                ),
                "content_id": attachment.get("content_id") or None,
                "inline": bool(attachment.get("inline")),
            }
        )
    return EmailMessageResponse(
        id=message.id,
        direction=message.direction,
        sender_email=message.sender_email,
        recipient_emails=message.recipient_emails,
        subject=message.subject,
        text_body=message.text_body,
        html_body=message.html_body,
        attachment_metadata=attachments,
        delivery_status=message.delivery_status,
        read_at=message.read_at,
        created_at=message.created_at,
    )


async def _parse_email_payload(
    request: Request,
    model_type: type[_EmailPayload],
) -> tuple[_EmailPayload, list[UploadFile]]:
    """Accept legacy JSON and multipart composer requests on the same internal endpoint."""
    uploads: list[UploadFile] = []
    content_type = request.headers.get("content-type", "").casefold()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        payload: dict[str, object] = {
            key: form.get(key)
            for key in (
                "to",
                "participant_name",
                "subject",
                "body",
                "html_body",
                "sender_profile",
                "idempotency_key",
            )
            if form.get(key) is not None
        }
        uploads = [item for item in form.getlist("attachments") if isinstance(item, UploadFile)]
    else:
        try:
            raw_payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raw_payload = None
        payload = raw_payload if isinstance(raw_payload, dict) else {}
    try:
        return model_type.model_validate(payload), uploads
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


def _thread_summary(
    thread: EmailThread,
    latest: EmailMessage | None,
) -> EmailThreadSummaryResponse:
    preview = latest.text_body.replace("\n", " ").strip()[:180] if latest else ""
    suggested_sender_profile = thread.sender_profile
    if suggested_sender_profile not in _MANUAL_SENDER_PROFILES:
        suggested_sender_profile = (
            thread.invite.sender_profile
            if thread.invite and thread.invite.sender_profile in _MANUAL_SENDER_PROFILES
            else "support"
        )
    return EmailThreadSummaryResponse(
        id=thread.id,
        invite_id=thread.invite_id,
        brand_id=thread.brand_id,
        brand_name=thread.brand.name if thread.brand else None,
        participant_email=thread.participant_email,
        participant_name=thread.participant_name,
        subject=thread.subject,
        status=thread.status,
        unread_count=thread.unread_count,
        last_message_at=thread.last_message_at,
        latest_preview=preview,
        latest_direction=latest.direction if latest else None,
        suggested_sender_profile=suggested_sender_profile,
        language=thread.language,
    )


def _thread_detail(thread: EmailThread) -> EmailThreadDetailResponse:
    latest = thread.messages[-1] if thread.messages else None
    summary = _thread_summary(thread, latest)
    return EmailThreadDetailResponse(
        **summary.model_dump(),
        messages=[_message_response(message) for message in thread.messages],
    )


async def _load_thread(db: AsyncSession, thread_id: int) -> EmailThread:
    thread = await db.scalar(
        select(EmailThread)
        .where(EmailThread.id == thread_id)
        .options(
            selectinload(EmailThread.messages),
            selectinload(EmailThread.brand),
            selectinload(EmailThread.invite),
        )
    )
    if thread is None:
        raise_error(404, ERR_EMAIL_THREAD_NOT_FOUND)
    return thread


async def _backfill_inline_attachment_ids(db: AsyncSession, thread: EmailThread) -> None:
    """Restore the link between an inline image and its attachment.

    Letters received before we started keeping content_id show a hole where the
    image belongs. The provider still knows the identifiers, so ask once per
    message and keep the answer.
    """
    refreshed = 0
    for message in thread.messages:
        if refreshed >= _MAX_BACKFILLED_MESSAGES_PER_THREAD:
            break
        if message.direction != "inbound" or not message.provider_message_id:
            continue
        if not message.html_body or not _CID_REFERENCE_PATTERN.search(message.html_body):
            continue
        stored = [item for item in message.attachment_metadata if isinstance(item, dict)]
        if not stored or all(
            item.get("content_id") or item.get("content_id_checked") for item in stored
        ):
            continue

        try:
            received = await run_in_threadpool(get_received_email, message.provider_message_id)
        except Exception:
            logger.warning(
                "Failed to refresh inline attachment identity for inbound email %s",
                message.provider_message_id,
                exc_info=True,
            )
            continue

        incoming = _attachment_metadata(received.get("attachments"))
        # A shorter answer means the provider no longer lists the same files;
        # keep what we stored rather than lose the filenames over an image.
        message.attachment_metadata = (
            incoming
            if len(incoming) == len(stored)
            else [{**item, "content_id_checked": True} for item in stored]
        )
        refreshed += 1

    if refreshed:
        await db.commit()


@dataclass(frozen=True)
class InboundEmailData:
    """One received email, already normalized by whichever transport delivered it."""

    participant_email: str
    participant_name: str | None
    subject: str
    body: str
    recipients: list[str]
    created_at: datetime
    provider_message_id: str
    provider_event_id: str | None
    internet_message_id: str | None
    in_reply_to: str | None
    attachment_metadata: list[dict]


async def ingest_inbound_email(db: AsyncSession, data: InboundEmailData) -> None:
    """Attach a received email to its thread, creating the thread when needed."""
    recipients = data.recipients
    participant_email = data.participant_email
    participant_name = data.participant_name
    subject = data.subject
    body = data.body
    created_at = data.created_at
    provider_email_id = data.provider_message_id
    stored_event_id = data.provider_event_id

    thread = None
    thread_token = _thread_token(recipients)
    if thread_token:
        thread = await db.scalar(
            select(EmailThread).where(EmailThread.reply_token == thread_token)
        )
        if thread is not None and thread.participant_email.casefold() != participant_email:
            logger.warning(
                "Inbound sender %s does not match email thread %s participant",
                participant_email,
                thread.id,
            )
            thread = None

    token = _reply_token(recipients)
    invite = None
    if thread is None and token:
        invite = await db.scalar(select(BrandInvite).where(BrandInvite.reply_token == token))

    invite_id = invite.id if invite else None
    invite_brand_id = invite.brand_id if invite else None
    if thread is None and invite is not None:
        thread = await db.scalar(
            select(EmailThread)
            .where(EmailThread.invite_id == invite_id)
        )
    if thread is None:
        thread = EmailThread(
            invite_id=invite_id,
            brand_id=invite_brand_id,
            participant_email=participant_email,
            participant_name=participant_name,
            subject=subject,
            reply_token=secrets.token_urlsafe(24),
            sender_profile=(
                invite.sender_profile
                if invite and invite.sender_profile in _MANUAL_SENDER_PROFILES
                else _sender_profile_for_recipients(recipients)
            ),
            language=invite.language if invite else DEFAULT_LANGUAGE,
            status="open",
            unread_count=0,
            last_message_at=created_at,
        )
        db.add(thread)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            if invite_id is None:
                raise
            # Two replies for the same invitation can arrive concurrently.
            # Keep both messages by reusing the thread created by the winner.
            thread = await db.scalar(
                select(EmailThread).where(EmailThread.invite_id == invite_id)
            )
            if thread is None:
                raise

    if thread.sender_profile not in _MANUAL_SENDER_PROFILES:
        thread.sender_profile = _sender_profile_for_recipients(recipients)
    _ensure_thread_reply_token(thread)
    message = EmailMessage(
        thread_id=thread.id,
        direction="inbound",
        sender_email=participant_email,
        recipient_emails=recipients,
        subject=subject,
        text_body=body,
        provider_message_id=provider_email_id,
        provider_event_id=stored_event_id,
        internet_message_id=data.internet_message_id,
        in_reply_to=data.in_reply_to,
        attachment_metadata=data.attachment_metadata,
        delivery_status="received",
        created_at=created_at,
    )
    db.add(message)
    thread.participant_email = participant_email
    thread.participant_name = participant_name or thread.participant_name
    thread.subject = subject
    thread.status = "open"
    thread.unread_count += 1
    thread.last_message_at = created_at
    thread.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info("Ignored duplicate inbound email event %s", stored_event_id)


@webhook_router.post("")
async def receive_resend_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """Verify, deduplicate and persist a Resend inbound email event."""
    if not settings.RESEND_WEBHOOK_SECRET or not settings.RESEND_API_KEY:
        raise_error(503, ERR_EMAIL_WEBHOOK_NOT_CONFIGURED)

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_WEBHOOK_BYTES:
        raise_error(413, ERR_EMAIL_WEBHOOK_INVALID)

    raw_body = await request.body()
    if not raw_body or len(raw_body) > _MAX_WEBHOOK_BYTES:
        raise_error(400, ERR_EMAIL_WEBHOOK_INVALID)

    event_id = request.headers.get("svix-id")
    timestamp = request.headers.get("svix-timestamp")
    signature = request.headers.get("svix-signature")
    if not event_id or not timestamp or not signature:
        raise_error(400, ERR_EMAIL_WEBHOOK_INVALID)

    try:
        payload_text = raw_body.decode("utf-8")
        _verify_svix_signature(
            raw_body=raw_body,
            event_id=event_id,
            timestamp=timestamp,
            signature=signature,
            secret=settings.RESEND_WEBHOOK_SECRET,
        )
        payload = json.loads(payload_text)
        if not isinstance(payload, dict):
            raise ValueError("Webhook payload must be an object")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        logger.warning("Rejected invalid Resend webhook")
        raise_error(400, ERR_EMAIL_WEBHOOK_INVALID)

    event_type = _header_value(payload.get("type"), 100)
    if event_type != "email.received":
        delivery_status = _DELIVERY_EVENT_STATUSES.get(event_type)
        event_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        provider_email_id = _header_value(event_data.get("email_id"), 100)
        if delivery_status and provider_email_id:
            message = await db.scalar(
                select(EmailMessage).where(
                    EmailMessage.provider_message_id == provider_email_id,
                    EmailMessage.direction == "outbound",
                )
            )
            if message is not None:
                message.delivery_status = _advance_delivery_status(
                    message.delivery_status,
                    delivery_status,
                )
                await db.commit()
        return {"received": True}

    stored_event_id = _header_value(event_id, 100)
    existing_event = await db.scalar(
        select(EmailMessage.id).where(EmailMessage.provider_event_id == stored_event_id)
    )
    if existing_event is not None:
        return {"received": True}

    event_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_email_id = _header_value(event_data.get("email_id"), 100)
    if not provider_email_id:
        raise_error(400, ERR_EMAIL_WEBHOOK_INVALID)

    existing_email = await db.scalar(
        select(EmailMessage.id).where(EmailMessage.provider_message_id == provider_email_id)
    )
    if existing_email is not None:
        return {"received": True}

    try:
        received = await run_in_threadpool(get_received_email, provider_email_id)
    except Exception:
        logger.error("Failed to retrieve inbound email %s", provider_email_id, exc_info=True)
        raise_error(502, ERR_EMAIL_INBOUND_FETCH_FAILED)

    recipients = _string_list(received.get("to") or event_data.get("to"))
    sender_raw = _truncate(received.get("from") or event_data.get("from"), 500)
    participant_name, participant_address = parseaddr(sender_raw)
    participant_email = _header_value(participant_address or sender_raw, 255).casefold()
    if not participant_email or "@" not in participant_email:
        raise_error(400, ERR_EMAIL_WEBHOOK_INVALID)
    headers = received.get("headers") if isinstance(received.get("headers"), dict) else {}

    await ingest_inbound_email(
        db,
        InboundEmailData(
            participant_email=participant_email,
            participant_name=_header_value(participant_name, 200) or None,
            subject=_header_value(received.get("subject") or event_data.get("subject"), 500)
            or "(no subject)",
            body=_plain_text(received.get("text"), received.get("html")),
            recipients=recipients,
            created_at=_parse_datetime(received.get("created_at") or event_data.get("created_at")),
            provider_message_id=provider_email_id,
            provider_event_id=stored_event_id,
            internet_message_id=_header_value(
                received.get("message_id") or event_data.get("message_id"), 500
            )
            or None,
            in_reply_to=_header_value(headers.get("in-reply-to"), 500) or None,
            attachment_metadata=_attachment_metadata(received.get("attachments")),
        ),
    )
    return {"received": True}


@admin_router.get("/email-threads", response_model=EmailThreadListResponse)
async def list_email_threads(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=50),
    status: Literal["open", "closed"] | None = None,
) -> EmailThreadListResponse:
    """List external email threads for administrators."""
    del admin
    filters = [EmailThread.status == status] if status else []
    total = int(
        await db.scalar(select(func.count(EmailThread.id)).where(*filters)) or 0
    )
    unread_total = int(
        await db.scalar(select(func.coalesce(func.sum(EmailThread.unread_count), 0))) or 0
    )
    latest_message_id = (
        select(EmailMessage.id)
        .where(EmailMessage.thread_id == EmailThread.id)
        .order_by(EmailMessage.created_at.desc(), EmailMessage.id.desc())
        .limit(1)
        .correlate(EmailThread)
        .scalar_subquery()
    )
    latest_message = aliased(EmailMessage)
    result = await db.execute(
        select(EmailThread, latest_message)
        .outerjoin(latest_message, latest_message.id == latest_message_id)
        .where(*filters)
        .options(
            selectinload(EmailThread.brand),
            selectinload(EmailThread.invite),
        )
        .order_by(EmailThread.last_message_at.desc(), EmailThread.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = result.unique().all()
    return EmailThreadListResponse(
        items=[_thread_summary(thread, latest) for thread, latest in rows],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size) if total else 0,
        unread_total=unread_total,
    )


@admin_router.post("/email-threads", response_model=EmailThreadDetailResponse, status_code=201)
@limiter.limit("60/hour")
async def create_email_thread(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailThreadDetailResponse:
    """Start an external email conversation from the administrative mailbox."""
    data, uploads = await _parse_email_payload(request, EmailThreadCreate)
    existing_message = await db.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == data.idempotency_key,
            EmailMessage.direction == "outbound",
        )
    )
    if existing_message is not None:
        return _thread_detail(await _load_thread(db, existing_message.thread_id))
    attachments = await prepare_email_attachments(uploads)
    sanitized_html = sanitize_admin_email_html(data.html_body)
    now = datetime.now(timezone.utc)
    participant_email = str(data.to).casefold()
    thread = EmailThread(
        participant_email=participant_email,
        participant_name=data.participant_name,
        subject=data.subject,
        reply_token=secrets.token_urlsafe(24),
        sender_profile=data.sender_profile,
        language=data.language,
        status="open",
        unread_count=0,
        last_message_at=now,
    )
    db.add(thread)
    await db.flush()

    result = await run_in_threadpool(
        send_admin_reply_email,
        to=participant_email,
        subject=data.subject,
        body=data.body,
        html_body=sanitized_html,
        sender_profile=data.sender_profile,
        participant_name=data.participant_name,
        reply_to=_thread_reply_address(thread),
        headers=None,
        attachments=[attachment.provider_payload() for attachment in attachments],
        idempotency_key=data.idempotency_key,
        language=data.language,
    )
    if not result.sent:
        await db.rollback()
        logger.error("Failed to start admin email thread: %s", result.error)
        raise_error(502, ERR_EMAIL_DELIVERY_FAILED)

    db.add(
        EmailMessage(
            thread_id=thread.id,
            direction="outbound",
            sender_email=get_email_sender(data.sender_profile),
            recipient_emails=[participant_email],
            subject=data.subject,
            text_body=data.body,
            html_body=sanitized_html,
            client_idempotency_key=data.idempotency_key,
            provider_message_id=result.provider_message_id,
            attachment_metadata=[attachment.metadata() for attachment in attachments],
            delivery_status="sent",
            sent_by_id=admin.id,
            read_at=now,
            created_at=now,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed_message = await db.scalar(
            select(EmailMessage).where(
                EmailMessage.client_idempotency_key == data.idempotency_key
            )
        )
        if replayed_message is None:
            raise
        return _thread_detail(await _load_thread(db, replayed_message.thread_id))
    return _thread_detail(await _load_thread(db, thread.id))


@admin_router.get("/email-threads/{thread_id}", response_model=EmailThreadDetailResponse)
async def get_email_thread(
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailThreadDetailResponse:
    del admin
    thread = await _load_thread(db, thread_id)
    await _backfill_inline_attachment_ids(db, thread)
    return _thread_detail(thread)


@admin_router.post("/email-threads/{thread_id}/read", response_model=EmailThreadDetailResponse)
async def mark_email_thread_read(
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailThreadDetailResponse:
    del admin
    thread = await _load_thread(db, thread_id)
    now = datetime.now(timezone.utc)
    await db.execute(
        update(EmailMessage)
        .where(
            EmailMessage.thread_id == thread.id,
            EmailMessage.direction == "inbound",
            EmailMessage.read_at.is_(None),
        )
        .values(read_at=now)
    )
    thread.unread_count = 0
    await db.commit()
    return _thread_detail(await _load_thread(db, thread_id))


@admin_router.patch("/email-threads/{thread_id}", response_model=EmailThreadDetailResponse)
async def update_email_thread(
    thread_id: int,
    data: EmailThreadStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailThreadDetailResponse:
    del admin
    thread = await _load_thread(db, thread_id)
    thread.status = data.status
    await db.commit()
    return _thread_detail(await _load_thread(db, thread_id))


@admin_router.delete("/email-threads/{thread_id}")
@limiter.limit("30/hour")
async def delete_email_thread(
    request: Request,
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, bool]:
    """Permanently delete an administrative email thread and all of its messages."""
    del admin
    thread = await _load_thread(db, thread_id)
    await db.delete(thread)
    await db.commit()
    return {"deleted": True}


@admin_router.get(
    "/email-threads/{thread_id}/messages/{message_id}/attachments/{attachment_index}"
)
@limiter.limit("60/hour")
async def download_email_attachment(
    request: Request,
    thread_id: int,
    message_id: int,
    attachment_index: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    """Proxy one inbound attachment through the authenticated backend."""
    del admin
    message = await db.scalar(
        select(EmailMessage).where(
            EmailMessage.id == message_id,
            EmailMessage.thread_id == thread_id,
            EmailMessage.direction == "inbound",
        )
    )
    if message is None or not message.provider_message_id:
        raise_error(404, ERR_EMAIL_ATTACHMENT_NOT_FOUND)
    if attachment_index < 0 or attachment_index >= len(message.attachment_metadata):
        raise_error(404, ERR_EMAIL_ATTACHMENT_NOT_FOUND)
    raw_attachment = message.attachment_metadata[attachment_index]
    if not isinstance(raw_attachment, dict):
        raise_error(404, ERR_EMAIL_ATTACHMENT_NOT_FOUND)
    # Locally delivered mail keeps the whole letter on disk, so the attachment is
    # read straight out of it instead of being fetched from a provider.
    from app.services.inbound_mail_service import read_stored_attachment

    local = await run_in_threadpool(
        read_stored_attachment, message.provider_event_id or "", attachment_index
    )
    if local is not None:
        content, content_type, local_name = local
        encoded_local_name = quote(local_name, safe="")
        return Response(
            content=content,
            media_type=content_type or "application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=\"attachment\"; filename*=UTF-8''{encoded_local_name}"
                ),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    attachment_id = str(raw_attachment.get("provider_attachment_id") or "")
    if not _RESEND_ATTACHMENT_ID_PATTERN.fullmatch(attachment_id):
        raise_error(404, ERR_EMAIL_ATTACHMENT_NOT_FOUND)

    try:
        attachment = await run_in_threadpool(
            get_received_email_attachment,
            message.provider_message_id,
            attachment_id,
        )
    except Exception:
        logger.error(
            "Failed to retrieve attachment %s for inbound email %s",
            attachment_id,
            message.provider_message_id,
            exc_info=True,
        )
        raise_error(502, ERR_EMAIL_ATTACHMENT_FETCH_FAILED)

    filename = _header_value(raw_attachment.get("filename"), 180) or "attachment"
    encoded_filename = quote(filename, safe="")
    content_type = attachment.content_type or raw_attachment.get("content_type")
    return Response(
        content=attachment.content,
        media_type=str(content_type or "application/octet-stream"),
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"attachment\"; filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@admin_router.post("/email-threads/{thread_id}/reply", response_model=EmailMessageResponse)
@limiter.limit("60/hour")
async def reply_to_email_thread(
    request: Request,
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailMessageResponse:
    """Reply through Resend while preserving the external email thread."""
    data, uploads = await _parse_email_payload(request, EmailThreadReplyCreate)
    existing_message = await db.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == data.idempotency_key,
            EmailMessage.direction == "outbound",
        )
    )
    if existing_message is not None:
        if existing_message.thread_id != thread_id:
            raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
        return _message_response(existing_message)
    attachments = await prepare_email_attachments(uploads)
    sanitized_html = sanitize_admin_email_html(data.html_body)
    thread = await _load_thread(db, thread_id)
    sender_profile = data.sender_profile or thread.sender_profile
    if sender_profile not in _MANUAL_SENDER_PROFILES:
        sender_profile = (
            thread.invite.sender_profile
            if thread.invite and thread.invite.sender_profile in _MANUAL_SENDER_PROFILES
            else "support"
        )
    subject = thread.subject if thread.subject.casefold().startswith("re:") else f"Re: {thread.subject}"
    latest_inbound = next(
        (message for message in reversed(thread.messages) if message.direction == "inbound"),
        None,
    )
    headers = None
    if latest_inbound and latest_inbound.internet_message_id:
        headers = {
            "In-Reply-To": latest_inbound.internet_message_id,
            "References": latest_inbound.internet_message_id,
        }
    reply_to = _thread_reply_address(thread)
    thread.sender_profile = sender_profile
    await db.flush()

    result = await run_in_threadpool(
        send_admin_reply_email,
        to=thread.participant_email,
        subject=subject,
        body=data.body,
        html_body=sanitized_html,
        sender_profile=sender_profile,
        participant_name=thread.participant_name,
        reply_to=reply_to,
        headers=headers,
        attachments=[attachment.provider_payload() for attachment in attachments],
        idempotency_key=data.idempotency_key,
        language=thread.language,
    )
    if not result.sent:
        logger.error("Failed to send admin email reply for thread %s: %s", thread.id, result.error)
        raise_error(502, ERR_EMAIL_DELIVERY_FAILED)

    now = datetime.now(timezone.utc)
    message = EmailMessage(
        thread_id=thread.id,
        direction="outbound",
        sender_email=get_email_sender(sender_profile),
        recipient_emails=[thread.participant_email],
        subject=subject,
        text_body=data.body,
        html_body=sanitized_html,
        client_idempotency_key=data.idempotency_key,
        provider_message_id=result.provider_message_id,
        in_reply_to=latest_inbound.internet_message_id if latest_inbound else None,
        attachment_metadata=[attachment.metadata() for attachment in attachments],
        delivery_status="sent",
        sent_by_id=admin.id,
        read_at=now,
        created_at=now,
    )
    db.add(message)
    thread.status = "open"
    thread.unread_count = 0
    thread.last_message_at = now
    thread.updated_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed_message = await db.scalar(
            select(EmailMessage).where(
                EmailMessage.client_idempotency_key == data.idempotency_key
            )
        )
        if replayed_message is None:
            raise
        return _message_response(replayed_message)
    await db.refresh(message)
    return _message_response(message)
