"""Read locally delivered mail and hand it to the shared inbound ingestion.

The mail server writes each message as a file; this service parses it and calls
the same ingestion the provider webhook uses. Files rather than an HTTP hook,
because the backend is not published outside the container network and a restart
during deploy must not lose a letter — unread files simply wait.
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path

from sqlalchemy import select, update

from app.api.v1.endpoints.email_communications import InboundEmailData, ingest_inbound_email
from app.core.config import settings
from app.models.email_communication import EmailMessage as StoredEmailMessage

logger = logging.getLogger(__name__)

_MAX_MESSAGE_BYTES = 20 * 1024 * 1024
_MAX_ATTACHMENTS = 50
_LOCAL_EVENT_PREFIX = "local:"
_last_maintenance_at: float | None = None
_mail_storage_state: dict[str, object] = {
    "ready": False,
    "over_quota": False,
    "total_bytes": 0,
    "quota_bytes": 0,
}


def _root() -> Path:
    return Path(settings.INBOUND_MAIL_DIR)


def _ensure_layout() -> tuple[Path, Path, Path, Path]:
    root = _root()
    incoming = root / "new"
    processing = root / "processing"
    stored = root / "stored"
    failed = root / "failed"
    for directory in (incoming, processing, stored, failed):
        directory.mkdir(parents=True, exist_ok=True)
    return incoming, processing, stored, failed


def _claim_pending(incoming: Path, processing: Path) -> list[Path]:
    """Atomically move available messages into this pass' processing area.

    Every Uvicorn worker may see the same directory listing, but a rename on the
    shared filesystem has only one winner. Losing workers simply skip the file.
    """
    claimed: list[Path] = []
    for source in sorted(incoming.glob("*.eml")):
        target = processing / source.name
        try:
            if target.exists():
                logger.warning(
                    "Could not claim inbound mail %s: processing target already exists",
                    source.name,
                )
                continue
            # Refresh the source before the atomic move. Maintenance running in
            # another worker must never mistake a just-claimed old delivery for
            # an abandoned claim. os.utime() fails instead of recreating a file
            # that another worker has already moved.
            os.utime(source, None)
            source.replace(target)
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Could not claim inbound mail %s", source.name, exc_info=True)
            continue
        claimed.append(target)
    return claimed


def _move_message(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    path.replace(destination / path.name)


def _read_and_parse(path: Path, event_id: str) -> InboundEmailData | None:
    raw = path.read_bytes()
    if len(raw) > _MAX_MESSAGE_BYTES:
        raise ValueError(f"message exceeds {_MAX_MESSAGE_BYTES} bytes")
    return parse_inbound_message(raw, event_id)


def delete_stored_messages(provider_event_ids: list[str]) -> int:
    """Delete raw local messages after their owning database records are gone."""
    deleted = 0
    for event_id in set(provider_event_ids):
        if not event_id.startswith(_LOCAL_EVENT_PREFIX):
            continue
        name = event_id.removeprefix(_LOCAL_EVENT_PREFIX)
        if not name or "/" in name or "\\" in name or ".." in name:
            continue
        event_deleted = False
        for directory_name in ("new", "processing", "stored", "failed"):
            path = _root() / directory_name / f"{name}.eml"
            try:
                path.unlink()
                event_deleted = True
            except FileNotFoundError:
                continue
            except OSError:
                logger.error(
                    "Could not delete raw inbound mail %s from %s",
                    path.name,
                    directory_name,
                    exc_info=True,
                )
        if event_deleted:
            deleted += 1
    return deleted


def _file_entries(directory: Path) -> list[tuple[Path, float, int]]:
    entries: list[tuple[Path, float, int]] = []
    for path in directory.glob("*.eml"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        entries.append((path, stat.st_mtime, stat.st_size))
    return entries


def mail_storage_health() -> dict[str, object]:
    """Last maintenance result, exposed without doing filesystem I/O per request."""
    return dict(_mail_storage_state)


def _storage_usage(
    incoming: Path,
    processing: Path,
    stored: Path,
    failed: Path,
) -> tuple[int, int]:
    protected = _file_entries(incoming) + _file_entries(processing)
    retained = _file_entries(stored) + _file_entries(failed)
    return (
        sum(size for _, _, size in protected + retained),
        sum(size for _, _, size in protected),
    )


async def _delete_orphaned_stored_mail(session_factory, stored: Path, now: float) -> int:
    grace = max(60, settings.INBOUND_MAIL_ORPHAN_GRACE_SECONDS)
    candidates = [
        path
        for path, modified_at, _ in _file_entries(stored)
        if now - modified_at >= grace
    ]
    if not candidates:
        return 0

    event_by_path = {
        path: f"{_LOCAL_EVENT_PREFIX}{path.stem}"
        for path in candidates
    }
    present: set[str] = set()
    event_ids = list(event_by_path.values())
    async with session_factory() as db:
        for offset in range(0, len(event_ids), 500):
            present.update(
                event_id
                for event_id in (
                    await db.scalars(
                        select(StoredEmailMessage.provider_event_id).where(
                            StoredEmailMessage.provider_event_id.in_(
                                event_ids[offset : offset + 500]
                            )
                        )
                    )
                ).all()
                if event_id
            )

    deleted = 0
    for path, event_id in event_by_path.items():
        if event_id in present:
            continue
        try:
            await asyncio.to_thread(path.unlink)
            deleted += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.error("Could not delete orphaned inbound mail %s", path.name, exc_info=True)
    return deleted


def _recover_stale_claims(processing: Path, incoming: Path, now: float) -> int:
    recovered = 0
    timeout = max(60, settings.INBOUND_MAIL_CLAIM_TIMEOUT_SECONDS)
    for path, modified_at, _ in _file_entries(processing):
        if now - modified_at < timeout:
            continue
        try:
            path.replace(incoming / path.name)
            recovered += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.error("Could not recover claimed inbound mail %s", path.name, exc_info=True)
    return recovered


def _retention_plan(
    incoming: Path,
    processing: Path,
    stored: Path,
    failed: Path,
    now: float,
) -> tuple[list[Path], list[Path]]:
    """Choose raw files to remove by age first, then by the bounded disk quota."""
    stored_entries = _file_entries(stored)
    failed_entries = _file_entries(failed)
    stored_cutoff = now - timedelta(
        days=max(1, settings.INBOUND_MAIL_STORED_RETENTION_DAYS)
    ).total_seconds()
    failed_cutoff = now - timedelta(
        days=max(1, settings.INBOUND_MAIL_FAILED_RETENTION_DAYS)
    ).total_seconds()

    stored_delete = {path for path, modified_at, _ in stored_entries if modified_at < stored_cutoff}
    failed_delete = {path for path, modified_at, _ in failed_entries if modified_at < failed_cutoff}

    all_entries = (
        _file_entries(incoming)
        + _file_entries(processing)
        + stored_entries
        + failed_entries
    )
    total_bytes = sum(size for _, _, size in all_entries)
    selected_bytes = sum(
        size
        for path, _, size in stored_entries + failed_entries
        if path in stored_delete or path in failed_delete
    )
    quota = max(_MAX_MESSAGE_BYTES, settings.INBOUND_MAIL_MAX_STORAGE_BYTES)
    remaining_bytes = max(0, total_bytes - selected_bytes)
    if remaining_bytes > quota:
        candidates = sorted(
            (
                (path, modified_at, size, "failed")
                for path, modified_at, size in failed_entries
                if path not in failed_delete
            ),
            key=lambda item: item[1],
        ) + sorted(
            (
                (path, modified_at, size, "stored")
                for path, modified_at, size in stored_entries
                if path not in stored_delete
            ),
            key=lambda item: item[1],
        )
        for path, _, size, kind in candidates:
            if remaining_bytes <= quota:
                break
            if kind == "failed":
                failed_delete.add(path)
            else:
                stored_delete.add(path)
            remaining_bytes -= size

    return sorted(stored_delete), sorted(failed_delete)


async def maintain_mail_storage(session_factory) -> None:
    """Recover abandoned claims and enforce raw-message retention and quota."""
    incoming, processing, stored, failed = await asyncio.to_thread(_ensure_layout)
    now = datetime.now(timezone.utc).timestamp()
    recovered = await asyncio.to_thread(_recover_stale_claims, processing, incoming, now)
    orphaned = await _delete_orphaned_stored_mail(session_factory, stored, now)
    stored_delete, failed_delete = await asyncio.to_thread(
        _retention_plan, incoming, processing, stored, failed, now
    )

    if stored_delete:
        event_ids = [f"{_LOCAL_EVENT_PREFIX}{path.stem}" for path in stored_delete]
        async with session_factory() as db:
            await db.execute(
                update(StoredEmailMessage)
                .where(StoredEmailMessage.provider_event_id.in_(event_ids))
                .values(provider_event_id=None)
            )
            await db.commit()
        await asyncio.to_thread(
            delete_stored_messages,
            event_ids,
        )

    for path in failed_delete:
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            continue
        except OSError:
            logger.error("Could not delete failed inbound mail %s", path.name, exc_info=True)

    total_bytes, protected_bytes = await asyncio.to_thread(
        _storage_usage,
        incoming,
        processing,
        stored,
        failed,
    )
    quota = max(_MAX_MESSAGE_BYTES, settings.INBOUND_MAIL_MAX_STORAGE_BYTES)
    over_quota = total_bytes > quota
    _mail_storage_state.update(
        {
            "ready": True,
            "over_quota": over_quota,
            "total_bytes": total_bytes,
            "quota_bytes": quota,
            "protected_bytes": protected_bytes,
        }
    )
    if over_quota:
        logger.error(
            "Inbound mail storage remains over quota after safe cleanup: "
            "total=%d quota=%d pending_or_processing=%d",
            total_bytes,
            quota,
            protected_bytes,
        )

    if recovered or orphaned or stored_delete or failed_delete:
        logger.info(
            "Inbound mail maintenance: recovered=%d orphaned=%d "
            "stored_deleted=%d failed_deleted=%d",
            recovered,
            orphaned,
            len(stored_delete),
            len(failed_delete),
        )


async def _maintain_mail_storage_if_due(session_factory) -> None:
    global _last_maintenance_at
    now = time.monotonic()
    interval = max(60, settings.INBOUND_MAIL_MAINTENANCE_SECONDS)
    if _last_maintenance_at is not None and now - _last_maintenance_at < interval:
        return
    await maintain_mail_storage(session_factory)
    _last_maintenance_at = now


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
    incoming, processing, stored, failed = await asyncio.to_thread(_ensure_layout)
    await _maintain_mail_storage_if_due(session_factory)
    accepted = 0
    claimed = await asyncio.to_thread(_claim_pending, incoming, processing)
    for path in claimed:
        event_id = f"{_LOCAL_EVENT_PREFIX}{path.stem}"
        try:
            data = await asyncio.to_thread(_read_and_parse, path, event_id)
            if data is None:
                await asyncio.to_thread(_move_message, path, failed)
                continue
            async with session_factory() as db:
                await ingest_inbound_email(db, data)
            try:
                await asyncio.to_thread(_move_message, path, stored)
            except (FileNotFoundError, OSError):
                # The database must not advertise a downloadable attachment if
                # its raw MIME file could not be retained.
                async with session_factory() as db:
                    await db.execute(
                        update(StoredEmailMessage)
                        .where(StoredEmailMessage.provider_event_id == event_id)
                        .values(provider_event_id=None)
                    )
                    await db.commit()
                raise
            accepted += 1
        except Exception:
            logger.error("Failed to ingest inbound mail %s", path.name, exc_info=True)
            try:
                await asyncio.to_thread(_move_message, path, failed)
            except (FileNotFoundError, OSError):
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
