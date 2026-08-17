"""Administrative communication inbox backed by locally delivered mail."""

import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser
from math import ceil
from typing import Annotated, Literal, TypeVar
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_EMAIL_ATTACHMENT_NOT_FOUND,
    ERR_EMAIL_DELIVERY_FAILED,
    ERR_EMAIL_DELIVERY_IN_PROGRESS,
    ERR_EMAIL_IDEMPOTENCY_CONFLICT,
    ERR_EMAIL_THREAD_NOT_FOUND,
    raise_error,
)
from app.core.i18n import DEFAULT_LANGUAGE
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.brand_invite import BrandInvite
from app.models.email_communication import EmailMessage, EmailSendReservation, EmailThread
from app.models.user import User
from app.schemas.email_communication import (
    EmailMessageResponse,
    EmailThreadCreate,
    EmailThreadDetailResponse,
    EmailThreadListResponse,
    EmailThreadReadRequest,
    EmailThreadReplyCreate,
    EmailThreadStatusUpdate,
    EmailThreadSummaryResponse,
)
from app.services.email_attachment_service import prepare_email_attachments
from app.services.email_service import (
    get_email_sender,
    outbound_send_is_stale,
    sanitize_admin_email_html,
    send_admin_reply_email,
)

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin/communications", tags=["admin"])

_MAX_BODY_CHARS = 100_000
_REPLY_TOKEN_PATTERN = re.compile(r"^invite-([A-Za-z0-9_-]{20,64})$")
_THREAD_TOKEN_PATTERN = re.compile(r"^thread-([A-Za-z0-9_-]{20,64})$")
_MANUAL_SENDER_PROFILES = {"support", "partnerships", "pr"}
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
                    and (message.provider_event_id or "").startswith("local:")
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


def _outbound_payload_matches(
    message: EmailMessage,
    *,
    thread_id: int | None,
    sender_email: str,
    recipient_email: str,
    subject: str,
    text_body: str,
    html_body: str | None,
    attachment_metadata: list[dict],
) -> bool:
    """Reject accidental reuse of an idempotency key for another email."""
    return (
        (thread_id is None or message.thread_id == thread_id)
        and message.sender_email == sender_email
        and message.recipient_emails == [recipient_email]
        and message.subject == subject
        and message.text_body == text_body
        and message.html_body == html_body
        and message.attachment_metadata == attachment_metadata
    )


async def _existing_outbound_message(
    db: AsyncSession,
    idempotency_key: str,
) -> EmailMessage | None:
    return await db.scalar(
        select(EmailMessage).where(
            EmailMessage.client_idempotency_key == idempotency_key,
            EmailMessage.direction == "outbound",
        )
    )


async def _email_key_was_reserved(db: AsyncSession, idempotency_key: str) -> bool:
    return (
        await db.scalar(
            select(EmailSendReservation.idempotency_key).where(
                EmailSendReservation.idempotency_key == idempotency_key
            )
        )
        is not None
    )


async def _reject_nonterminal_replay(db: AsyncSession, message: EmailMessage) -> None:
    if message.delivery_status != "sending":
        return
    if outbound_send_is_stale(message.created_at):
        message.delivery_status = "failed"
        await db.commit()
        raise_error(502, ERR_EMAIL_DELIVERY_FAILED)
    raise_error(409, ERR_EMAIL_DELIVERY_IN_PROGRESS)


async def _reject_active_thread_sends(db: AsyncSession, thread: EmailThread) -> None:
    active = False
    for message in thread.messages:
        if message.delivery_status != "sending":
            continue
        if outbound_send_is_stale(message.created_at):
            message.delivery_status = "failed"
        else:
            active = True
    if active:
        raise_error(409, ERR_EMAIL_DELIVERY_IN_PROGRESS)


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


async def _load_thread(
    db: AsyncSession,
    thread_id: int,
    *,
    for_update: bool = False,
) -> EmailThread:
    statement = (
        select(EmailThread)
        .where(EmailThread.id == thread_id)
        .options(
            selectinload(EmailThread.messages),
            selectinload(EmailThread.brand),
            selectinload(EmailThread.invite),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    thread = await db.scalar(statement)
    if thread is None:
        raise_error(404, ERR_EMAIL_THREAD_NOT_FOUND)
    return thread


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
            select(EmailThread)
            .where(EmailThread.reply_token == thread_token)
            .with_for_update()
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
            .with_for_update()
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
                select(EmailThread)
                .where(EmailThread.invite_id == invite_id)
                .with_for_update()
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
    is_latest = EmailThread.last_message_at <= created_at
    thread_values: dict[str, object] = {
        "participant_email": case(
            (is_latest, participant_email), else_=EmailThread.participant_email
        ),
        "subject": case((is_latest, subject), else_=EmailThread.subject),
        "status": "open",
        "unread_count": EmailThread.unread_count + 1,
        "last_message_at": case(
            (is_latest, created_at), else_=EmailThread.last_message_at
        ),
        "updated_at": datetime.now(timezone.utc),
    }
    if participant_name:
        thread_values["participant_name"] = case(
            (is_latest, participant_name), else_=EmailThread.participant_name
        )
    try:
        # Flush the message inside the duplicate guard. ``execute`` below also
        # triggers autoflush, so leaving it outside this block lets a repeated
        # provider id raise before the IntegrityError handler can classify it
        # as the already-processed delivery that it is.
        await db.flush()
        await db.execute(
            update(EmailThread)
            .where(EmailThread.id == thread.id)
            .values(**thread_values)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info("Ignored duplicate inbound email event %s", stored_event_id)


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
    attachments = await prepare_email_attachments(uploads)
    attachment_metadata = [attachment.metadata() for attachment in attachments]
    sanitized_html = sanitize_admin_email_html(data.html_body)
    now = datetime.now(timezone.utc)
    participant_email = str(data.to).casefold()
    sender_email = get_email_sender(data.sender_profile)
    existing_message = await _existing_outbound_message(db, data.idempotency_key)
    if existing_message is not None:
        existing_thread = await _load_thread(db, existing_message.thread_id)
        if not _outbound_payload_matches(
            existing_message,
            thread_id=None,
            sender_email=sender_email,
            recipient_email=participant_email,
            subject=data.subject,
            text_body=data.body,
            html_body=sanitized_html,
            attachment_metadata=attachment_metadata,
        ) or existing_thread.participant_name != data.participant_name or (
            existing_thread.language != data.language
        ):
            raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
        if existing_message.delivery_status == "failed":
            raise_error(502, ERR_EMAIL_DELIVERY_FAILED)
        await _reject_nonterminal_replay(db, existing_message)
        return _thread_detail(existing_thread)
    if await _email_key_was_reserved(db, data.idempotency_key):
        raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)

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
    message = EmailMessage(
        thread_id=thread.id,
        direction="outbound",
        sender_email=sender_email,
        recipient_emails=[participant_email],
        subject=data.subject,
        text_body=data.body,
        html_body=sanitized_html,
        client_idempotency_key=data.idempotency_key,
        attachment_metadata=attachment_metadata,
        delivery_status="sending",
        sent_by_id=admin.id,
        read_at=now,
        created_at=now,
    )
    db.add(message)
    db.add(EmailSendReservation(idempotency_key=data.idempotency_key))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed_message = await _existing_outbound_message(db, data.idempotency_key)
        if replayed_message is None:
            if await _email_key_was_reserved(db, data.idempotency_key):
                raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
            raise
        replayed_thread = await _load_thread(db, replayed_message.thread_id)
        if not _outbound_payload_matches(
            replayed_message,
            thread_id=None,
            sender_email=sender_email,
            recipient_email=participant_email,
            subject=data.subject,
            text_body=data.body,
            html_body=sanitized_html,
            attachment_metadata=attachment_metadata,
        ) or replayed_thread.participant_name != data.participant_name or (
            replayed_thread.language != data.language
        ):
            raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
        if replayed_message.delivery_status == "failed":
            raise_error(502, ERR_EMAIL_DELIVERY_FAILED)
        await _reject_nonterminal_replay(db, replayed_message)
        return _thread_detail(replayed_thread)

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
        message.delivery_status = "failed"
        await db.commit()
        logger.error("Failed to start admin email thread: %s", result.error)
        raise_error(502, ERR_EMAIL_DELIVERY_FAILED)

    message.provider_message_id = result.provider_message_id
    message.delivery_status = "sent"
    await db.commit()
    return _thread_detail(await _load_thread(db, thread.id))


@admin_router.get("/email-threads/{thread_id}", response_model=EmailThreadDetailResponse)
async def get_email_thread(
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailThreadDetailResponse:
    del admin
    thread = await _load_thread(db, thread_id)
    return _thread_detail(thread)


@admin_router.post("/email-threads/{thread_id}/read", response_model=EmailThreadDetailResponse)
async def mark_email_thread_read(
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
    data: Annotated[EmailThreadReadRequest | None, Body()] = None,
) -> EmailThreadDetailResponse:
    del admin
    thread = await _load_thread(db, thread_id, for_update=True)
    through_message_id = data.through_message_id if data else None
    if through_message_id is None:
        through_message_id = await db.scalar(
            select(func.max(EmailMessage.id)).where(
                EmailMessage.thread_id == thread.id,
                EmailMessage.direction == "inbound",
            )
        )
    now = datetime.now(timezone.utc)
    if through_message_id is not None:
        await db.execute(
            update(EmailMessage)
            .where(
                EmailMessage.thread_id == thread.id,
                EmailMessage.direction == "inbound",
                EmailMessage.id <= through_message_id,
                EmailMessage.read_at.is_(None),
            )
            .values(read_at=now)
        )
    thread.unread_count = int(
        await db.scalar(
            select(func.count(EmailMessage.id)).where(
                EmailMessage.thread_id == thread.id,
                EmailMessage.direction == "inbound",
                EmailMessage.read_at.is_(None),
            )
        )
        or 0
    )
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
    thread = await _load_thread(db, thread_id, for_update=True)
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
    thread = await _load_thread(db, thread_id, for_update=True)
    await _reject_active_thread_sends(db, thread)
    stored_mail_event_ids = [
        message.provider_event_id
        for message in thread.messages
        if (message.provider_event_id or "").startswith("local:")
    ]
    await db.delete(thread)
    await db.commit()
    if stored_mail_event_ids:
        from app.services.inbound_mail_service import delete_stored_messages

        deleted = await run_in_threadpool(delete_stored_messages, stored_mail_event_ids)
        if deleted != len(stored_mail_event_ids):
            logger.warning(
                "Deleted %d of %d raw inbound messages for thread_id=%d",
                deleted,
                len(stored_mail_event_ids),
                thread_id,
            )
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
    # read straight out of it without exposing the mail spool to the browser.
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

    # Historical provider-backed messages may still contain attachment metadata,
    # but their remote content is intentionally no longer fetched after the
    # receiving path moved to our own server.
    raise_error(404, ERR_EMAIL_ATTACHMENT_NOT_FOUND)


@admin_router.post("/email-threads/{thread_id}/reply", response_model=EmailMessageResponse)
@limiter.limit("60/hour")
async def reply_to_email_thread(
    request: Request,
    thread_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> EmailMessageResponse:
    """Reply through the configured SMTP relay while preserving the email thread."""
    data, uploads = await _parse_email_payload(request, EmailThreadReplyCreate)
    attachments = await prepare_email_attachments(uploads)
    attachment_metadata = [attachment.metadata() for attachment in attachments]
    sanitized_html = sanitize_admin_email_html(data.html_body)
    thread = await _load_thread(db, thread_id, for_update=True)
    participant_email = thread.participant_email
    sender_profile = data.sender_profile or thread.sender_profile
    if sender_profile not in _MANUAL_SENDER_PROFILES:
        sender_profile = (
            thread.invite.sender_profile
            if thread.invite and thread.invite.sender_profile in _MANUAL_SENDER_PROFILES
            else "support"
        )
    sender_email = get_email_sender(sender_profile)
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
    now = datetime.now(timezone.utc)
    existing_message = await _existing_outbound_message(db, data.idempotency_key)
    if existing_message is not None:
        if not _outbound_payload_matches(
            existing_message,
            thread_id=thread_id,
            sender_email=sender_email,
            recipient_email=participant_email,
            subject=subject,
            text_body=data.body,
            html_body=sanitized_html,
            attachment_metadata=attachment_metadata,
        ):
            raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
        if existing_message.delivery_status == "failed":
            raise_error(502, ERR_EMAIL_DELIVERY_FAILED)
        await _reject_nonterminal_replay(db, existing_message)
        return _message_response(existing_message)
    if await _email_key_was_reserved(db, data.idempotency_key):
        raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)

    message = EmailMessage(
        thread_id=thread.id,
        direction="outbound",
        sender_email=sender_email,
        recipient_emails=[participant_email],
        subject=subject,
        text_body=data.body,
        html_body=sanitized_html,
        client_idempotency_key=data.idempotency_key,
        in_reply_to=latest_inbound.internet_message_id if latest_inbound else None,
        attachment_metadata=attachment_metadata,
        delivery_status="sending",
        sent_by_id=admin.id,
        read_at=now,
        created_at=now,
    )
    db.add(message)
    db.add(EmailSendReservation(idempotency_key=data.idempotency_key))
    thread.status = "open"
    thread.last_message_at = now
    thread.updated_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed_message = await _existing_outbound_message(db, data.idempotency_key)
        if replayed_message is None:
            if await _email_key_was_reserved(db, data.idempotency_key):
                raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
            raise
        if not _outbound_payload_matches(
            replayed_message,
            thread_id=thread_id,
            sender_email=sender_email,
            recipient_email=participant_email,
            subject=subject,
            text_body=data.body,
            html_body=sanitized_html,
            attachment_metadata=attachment_metadata,
        ):
            raise_error(409, ERR_EMAIL_IDEMPOTENCY_CONFLICT)
        if replayed_message.delivery_status == "failed":
            raise_error(502, ERR_EMAIL_DELIVERY_FAILED)
        await _reject_nonterminal_replay(db, replayed_message)
        return _message_response(replayed_message)

    result = await run_in_threadpool(
        send_admin_reply_email,
        to=participant_email,
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
        message.delivery_status = "failed"
        await db.commit()
        logger.error("Failed to send admin email reply for thread %s: %s", thread.id, result.error)
        raise_error(502, ERR_EMAIL_DELIVERY_FAILED)

    message.provider_message_id = result.provider_message_id
    message.delivery_status = "sent"
    await db.commit()
    await db.refresh(message)
    return _message_response(message)
