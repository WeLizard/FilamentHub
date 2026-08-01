"""Read locally delivered mail and hand it to the shared inbound ingestion.

The mail server writes each message as a file; this service parses it and calls
the same ingestion the provider webhook uses. Files rather than an HTTP hook,
because the backend is not published outside the container network and a restart
during deploy must not lose a letter — unread files simply wait.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

from app.api.v1.endpoints.email_communications import InboundEmailData, ingest_inbound_email
from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_MESSAGE_BYTES = 20 * 1024 * 1024
_MAX_ATTACHMENTS = 50
_LOCAL_EVENT_PREFIX = "local:"


def _root() -> Path:
    return Path(settings.INBOUND_MAIL_DIR)


def _ensure_layout() -> tuple[Path, Path, Path]:
    root = _root()
    incoming, stored, failed = root / "new", root / "stored", root / "failed"
    for directory in (incoming, stored, failed):
        directory.mkdir(parents=True, exist_ok=True)
    return incoming, stored, failed


def _addresses(message: EmailMessage) -> list[str]:
    """Every address the letter was routed to, including the envelope recipient.

    The thread token usually lives in the envelope rather than in To:, and the
    mail server records that in X-Original-To on delivery.
    """
    values: list[str] = []
    for header in ("X-Original-To", "Delivered-To", "To", "Cc"):
        for raw in message.get_all(header, []):
            text = str(raw).strip()
            if text:
                values.append(text[:500])
    return values[:50]


def _bodies(message: EmailMessage) -> tuple[str, str]:
    text = html = ""
    if message.is_multipart():
        text_part = message.get_body(preferencelist=("plain",))
        html_part = message.get_body(preferencelist=("html",))
    else:
        text_part = message if message.get_content_type() == "text/plain" else None
        html_part = message if message.get_content_type() == "text/html" else None
    for part, sink in ((text_part, "text"), (html_part, "html")):
        if part is None:
            continue
        try:
            content = part.get_content()
        except Exception:
            logger.warning("Unreadable %s part in inbound mail", sink, exc_info=True)
            continue
        if sink == "text":
            text = str(content)
        else:
            html = str(content)
    return text, html


def _attachments(message: EmailMessage) -> list[dict]:
    attachments: list[dict] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").casefold()
        if not filename and disposition != "inline":
            continue
        try:
            size = len(part.get_payload(decode=True) or b"")
        except Exception:
            size = None
        content_id = (part.get("Content-ID") or "").strip().lstrip("<").rstrip(">") or None
        attachments.append(
            {
                "filename": (filename or "attachment").replace("\\", "/").rsplit("/", 1)[-1],
                "content_type": part.get_content_type(),
                "size": size,
                # Local mail has no provider-side id; the index into this list is
                # what the download endpoint resolves against the stored file.
                "provider_attachment_id": None,
                "content_id": content_id,
                "inline": disposition == "inline",
                "content_id_checked": True,
            }
        )
        if len(attachments) >= _MAX_ATTACHMENTS:
            break
    return attachments


def parse_inbound_message(raw: bytes, event_id: str) -> InboundEmailData | None:
    """Turn a delivered file into the shape the ingestion expects."""
    message = message_from_bytes(raw, policy=policy.default)
    sender = message.get("From", "")
    _, address = _split_address(str(sender))
    if not address or "@" not in address:
        logger.warning("Inbound mail %s has no usable sender", event_id)
        return None

    text, html = _bodies(message)
    try:
        created_at = parsedate_to_datetime(message.get("Date", ""))
    except (TypeError, ValueError):
        created_at = None
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    elif created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    display_name, _ = _split_address(str(sender))
    return InboundEmailData(
        participant_email=address.casefold()[:255],
        participant_name=(display_name or None),
        subject=(str(message.get("Subject", "")).strip() or "(no subject)")[:500],
        body=_plain_body(text, html),
        recipients=_addresses(message),
        created_at=created_at,
        provider_message_id=(str(message.get("Message-ID", "")).strip() or event_id)[:100],
        provider_event_id=event_id[:100],
        internet_message_id=(str(message.get("Message-ID", "")).strip() or None),
        in_reply_to=(str(message.get("In-Reply-To", "")).strip() or None),
        attachment_metadata=_attachments(message),
    )


def _split_address(value: str) -> tuple[str, str]:
    from email.utils import parseaddr

    name, address = parseaddr(value)
    return name.strip()[:200], address.strip()


def _plain_body(text: str, html: str) -> str:
    from app.api.v1.endpoints.email_communications import _plain_text

    return _plain_text(text, html)


def stored_message_path(provider_event_id: str) -> Path | None:
    """Locate the kept file for a locally delivered message."""
    if not provider_event_id.startswith(_LOCAL_EVENT_PREFIX):
        return None
    name = provider_event_id.removeprefix(_LOCAL_EVENT_PREFIX)
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    candidate = _root() / "stored" / f"{name}.eml"
    return candidate if candidate.is_file() else None


def read_stored_attachment(provider_event_id: str, index: int) -> tuple[bytes, str, str] | None:
    """Extract one attachment straight from the kept message file."""
    path = stored_message_path(provider_event_id)
    if path is None or index < 0:
        return None
    message = message_from_bytes(path.read_bytes(), policy=policy.default)
    position = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").casefold()
        if not filename and disposition != "inline":
            continue
        if position == index:
            content = part.get_payload(decode=True) or b""
            name = (filename or "attachment").replace("\\", "/").rsplit("/", 1)[-1]
            return content, part.get_content_type(), name
        position += 1
    return None


async def process_pending_mail(session_factory) -> int:
    """Ingest every delivered file once. Returns how many letters were accepted."""
    incoming, stored, failed = _ensure_layout()
    accepted = 0
    for path in sorted(incoming.glob("*.eml")):
        event_id = f"{_LOCAL_EVENT_PREFIX}{path.stem}"
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_MESSAGE_BYTES:
                raise ValueError(f"message exceeds {_MAX_MESSAGE_BYTES} bytes")
            data = parse_inbound_message(raw, event_id)
            if data is None:
                path.rename(failed / path.name)
                continue
            async with session_factory() as db:
                await ingest_inbound_email(db, data)
            path.rename(stored / path.name)
            accepted += 1
        except Exception:
            logger.error("Failed to ingest inbound mail %s", path.name, exc_info=True)
            try:
                path.rename(failed / path.name)
            except OSError:
                logger.error("Could not quarantine inbound mail %s", path.name, exc_info=True)
    return accepted


async def run_inbound_mail_poller(session_factory) -> None:
    """Scan the delivery directory forever; a local directory listing is cheap."""
    interval = max(5, settings.INBOUND_MAIL_POLL_SECONDS)
    while True:
        try:
            await process_pending_mail(session_factory)
        except Exception:
            logger.error("Inbound mail poller pass failed", exc_info=True)
        await asyncio.sleep(interval)


def new_message_name() -> str:
    return f"{uuid.uuid4().hex}.eml"
