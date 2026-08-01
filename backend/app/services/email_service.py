"""Outgoing mail over SMTP; inbound still arrives through the Resend webhook."""

import base64
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from urllib.parse import urlparse

import httpx
import nh3
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.core.config import settings
from app.core.i18n import resolve_language, translate, translate_html, translate_list

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_RESEND_RECEIVING_URL = "https://api.resend.com/emails/receiving"
_RESEND_EMAIL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_RESEND_ATTACHMENT_DOWNLOAD_HOSTS = {"cdn.resend.app"}
_MAX_RECEIVED_ATTACHMENT_BYTES = 15 * 1024 * 1024
_ADMIN_EMAIL_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h2",
    "h3",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
}
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, *, language: str | None = None, **context: object) -> str:
    """Render an email template from app/templates/email in the recipient's language."""
    lang = resolve_language(language)
    return _jinja_env.get_template(template_name).render(
        lang=lang,
        t=lambda key, **params: translate(key, lang, **params),
        t_html=lambda key, **params: translate_html(key, lang, **params),
        t_list=lambda key: translate_list(key, lang),
        **context,
    )


def _is_configured() -> bool:
    """Whether outgoing mail can be handed to the relay."""
    return bool(settings.SMTP_USER and settings.SMTP_PASSWORD)


def _is_inbound_configured() -> bool:
    """Inbound still goes through the Resend API and has its own credential."""
    return bool(settings.RESEND_API_KEY)


@dataclass(frozen=True)
class EmailSendResult:
    """Provider result kept explicit for admin delivery tracking."""

    sent: bool
    provider_message_id: str | None = None
    error: str | None = None

    def __bool__(self) -> bool:
        return self.sent


@dataclass(frozen=True)
class ReceivedEmailAttachment:
    """Bounded content downloaded from an authenticated Resend attachment URL."""

    content: bytes
    content_type: str | None


def _received_attachment_content_type(content: bytes, declared: str | None) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return declared


def _get_from(profile: str = "transactional") -> str:
    addresses = {
        "transactional": settings.EMAIL_FROM,
        "support": settings.EMAIL_CONTACT,
        "partnerships": settings.EMAIL_PARTNERSHIPS_FROM,
        "pr": settings.EMAIL_PR_FROM,
    }
    if profile not in addresses:
        raise ValueError(f"Unknown email sender profile: {profile}")
    return f"{settings.EMAIL_FROM_NAME} <{addresses[profile]}>"


def _sender_domain() -> str:
    return settings.EMAIL_FROM.rpartition("@")[2] or "filamenthub.ru"


def _build_message(
    *,
    from_address: str,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
    attachments: list[dict[str, str]] | None = None,
) -> EmailMessage:
    """Assemble the MIME message the relay will hand over verbatim."""
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=_sender_domain())
    if reply_to:
        message["Reply-To"] = reply_to
    for name, value in (headers or {}).items():
        # Threading headers are set by the caller and must not be duplicated.
        del message[name]
        message[name] = value

    if text:
        message.set_content(text)
        message.add_alternative(html, subtype="html")
    else:
        message.set_content(html, subtype="html")

    for attachment in attachments or []:
        maintype, _, subtype = (attachment.get("content_type") or "application/octet-stream").partition("/")
        message.add_attachment(
            base64.b64decode(attachment["content"]),
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=attachment["filename"],
        )
    return message


def _deliver(message: EmailMessage) -> None:
    """Hand the message to the relay, raising on any delivery problem."""
    context = ssl.create_default_context()
    timeout = settings.SMTP_TIMEOUT_SECONDS
    if settings.SMTP_PORT == 465:
        with smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context
        ) as smtp:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
        return
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout) as smtp:
        smtp.starttls(context=context)
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send a single email. Returns True on success, False if not configured or on error."""
    if not _is_configured():
        logger.warning("Email sending skipped: SMTP credentials are not configured")
        return False

    try:
        _deliver(_build_message(from_address=_get_from(), to=to, subject=subject, html=html))
        return True
    except Exception:
        logger.error("Failed to send email to %s", to, exc_info=True)
        return False


ADMIN_REPLY_TEMPLATES = {
    "support": "admin_reply_plain.html",
    "transactional": "admin_reply_plain.html",
    "partnerships": "admin_reply.html",
    "pr": "admin_reply.html",
}


def format_recipient(address: str, name: str | None) -> str:
    """Address a letter to a person, not to a mailbox."""
    forbidden = set(chr(34) + chr(92) + "<>,;" + chr(13) + chr(10))
    clean_name = "".join(
        char for char in (name or "").strip()
        if char.isprintable() and char not in forbidden
    ).strip()
    if not clean_name:
        return address
    return chr(34) + clean_name + chr(34) + " <" + address + ">"


def send_email_tracked(
    *,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    sender_profile: str = "transactional",
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
    attachments: list[dict[str, str]] | None = None,
    idempotency_key: str | None = None,
) -> EmailSendResult:
    """Send email and return a trackable result.

    `idempotency_key` is accepted for call-site symmetry but no longer travels to
    a provider: duplicate suppression is the unique index on the stored key.
    """
    if not _is_configured():
        logger.warning("Email sending skipped: SMTP credentials are not configured")
        return EmailSendResult(sent=False, error="SMTP credentials are not configured")

    try:
        from_address = _get_from(sender_profile)
    except ValueError as exc:
        return EmailSendResult(sent=False, error=str(exc))

    try:
        message = _build_message(
            from_address=from_address,
            to=to,
            subject=subject,
            html=html,
            text=text,
            reply_to=reply_to,
            headers=headers,
            attachments=attachments,
        )
        _deliver(message)
        return EmailSendResult(sent=True, provider_message_id=message["Message-ID"].strip("<>"))
    except Exception as exc:
        logger.error("Failed to send tracked email to %s", to, exc_info=True)
        return EmailSendResult(sent=False, error=str(exc)[:500])


def get_email_sender(profile: str) -> str:
    """Return the configured sender identity for persistence and UI display."""
    return _get_from(profile)


def get_received_email(email_id: str) -> dict:
    """Retrieve full content for a verified Resend inbound event."""
    if not _is_inbound_configured():
        raise RuntimeError("RESEND_API_KEY is not configured")
    if not _RESEND_EMAIL_ID_PATTERN.fullmatch(email_id):
        raise ValueError("Invalid Resend received email ID")

    response = httpx.get(
        f"{_RESEND_RECEIVING_URL}/{email_id}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        params={"html_format": "cid"},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Resend received email response")
    return payload


def get_received_email_attachment(email_id: str, attachment_id: str) -> ReceivedEmailAttachment:
    """Retrieve one inbound attachment without exposing the provider's signed URL."""
    if not _is_inbound_configured():
        raise RuntimeError("RESEND_API_KEY is not configured")
    if not _RESEND_EMAIL_ID_PATTERN.fullmatch(email_id) or not _RESEND_EMAIL_ID_PATTERN.fullmatch(
        attachment_id
    ):
        raise ValueError("Invalid Resend attachment identity")

    metadata_response = httpx.get(
        f"{_RESEND_RECEIVING_URL}/{email_id}/attachments/{attachment_id}",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        timeout=15.0,
    )
    metadata_response.raise_for_status()
    metadata = metadata_response.json()
    if not isinstance(metadata, dict):
        raise RuntimeError("Unexpected Resend attachment response")
    download_url = metadata.get("download_url")
    parsed_url = urlparse(str(download_url or ""))
    hostname = (parsed_url.hostname or "").casefold()
    if parsed_url.scheme != "https" or not (
        hostname in _RESEND_ATTACHMENT_DOWNLOAD_HOSTS
        or hostname == "resend.com"
        or hostname.endswith(".resend.com")
    ):
        raise RuntimeError("Unexpected Resend attachment download URL")

    chunks: list[bytes] = []
    size = 0
    with httpx.stream("GET", str(download_url), timeout=20.0, follow_redirects=False) as response:
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > _MAX_RECEIVED_ATTACHMENT_BYTES:
            raise RuntimeError("Inbound attachment exceeds the download limit")
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > _MAX_RECEIVED_ATTACHMENT_BYTES:
                raise RuntimeError("Inbound attachment exceeds the download limit")
            chunks.append(chunk)
        content_type = response.headers.get("content-type")
    content = b"".join(chunks)
    return ReceivedEmailAttachment(
        content=content,
        content_type=_received_attachment_content_type(content, content_type),
    )


def sanitize_admin_email_html(value: str | None) -> str | None:
    """Reduce editor HTML to the small formatting vocabulary allowed in email."""
    if not value:
        return None
    cleaned = nh3.clean(
        value,
        tags=_ADMIN_EMAIL_TAGS,
        attributes={"a": {"href", "title"}},
        clean_content_tags={"iframe", "object", "script", "style", "svg", "template"},
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
        strip_comments=True,
    ).strip()
    return cleaned or None


def send_admin_reply_email(
    *,
    to: str,
    subject: str,
    body: str,
    html_body: str | None,
    sender_profile: str,
    participant_name: str | None = None,
    reply_to: str | None,
    headers: dict[str, str] | None = None,
    attachments: list[dict[str, str]] | None = None,
    idempotency_key: str | None = None,
    language: str | None = None,
) -> EmailSendResult:
    """Send sanitized authored content using the shared branded email template."""
    sanitized_html = sanitize_admin_email_html(html_body)
    html = _render(
        ADMIN_REPLY_TEMPLATES.get(sender_profile, "admin_reply.html"),
        language=language,
        subject=subject,
        body=body,
        body_html=Markup(sanitized_html) if sanitized_html else None,
        contact_email=settings.EMAIL_CONTACT,
    )
    return send_email_tracked(
        to=format_recipient(to, participant_name),
        subject=subject,
        html=html,
        text=body,
        sender_profile=sender_profile,
        reply_to=reply_to,
        headers=headers,
        attachments=attachments,
        idempotency_key=idempotency_key,
    )


def send_password_reset_email(*, to: str, reset_url: str, language: str | None = None) -> bool:
    """Send password reset link."""
    subject = translate("passwordReset.subject", language)
    html = _render("password_reset.html", language=language, subject=subject, reset_url=reset_url)
    return send_email(to=to, subject=subject, html=html)


def send_email_verification_email(
    *, to: str, verify_url: str, reject_url: str, language: str | None = None
) -> bool:
    """Ask a new account to confirm the address, or to disown it if it is not theirs."""
    subject = translate("emailVerification.subject", language)
    html = _render(
        "email_verification.html",
        language=language,
        subject=subject,
        verify_url=verify_url,
        reject_url=reject_url,
    )
    return send_email(to=to, subject=subject, html=html)


def send_email_change_email(*, to: str, confirm_url: str, language: str | None = None) -> bool:
    """Send email change confirmation to the new address."""
    subject = translate("emailChange.subject", language)
    html = _render("email_change.html", language=language, subject=subject, confirm_url=confirm_url)
    return send_email(to=to, subject=subject, html=html)


def send_brand_status_email(
    *,
    to: str,
    brand_name: str,
    approved: bool,
    reason: str | None = None,
    language: str | None = None,
) -> bool:
    """Send brand verification status notification."""
    subject = translate(
        "brandStatus.subjectApproved" if approved else "brandStatus.subjectRejected",
        language,
        brand_name=brand_name,
    )
    html = _render(
        "brand_status.html",
        language=language,
        subject=subject,
        brand_name=brand_name,
        approved=approved,
        reason=reason,
    )
    return send_email(to=to, subject=subject, html=html)


def send_brand_invite_email(
    *,
    to: str,
    brand_name: str | None,
    invite_url: str,
    site_url: str,
    sender_profile: str = "partnerships",
    reply_to: str | None = None,
    language: str | None = None,
) -> EmailSendResult:
    """Send a pre-verified brand invitation to a manufacturer's corporate email."""
    brand_display = brand_name or translate("brandInvite.brandFallback", language)
    subject = (
        translate("brandInvite.subject", language, brand_name=brand_name)
        if brand_name
        else translate("brandInvite.subjectGeneric", language)
    )
    html = _render(
        "brand_invite.html",
        language=language,
        subject=subject,
        brand_display=brand_display,
        invite_url=invite_url,
        site_url=site_url,
        contact_email=settings.EMAIL_CONTACT,
    )
    return send_email_tracked(
        to=to,
        subject=subject,
        html=html,
        sender_profile=sender_profile,
        reply_to=reply_to,
        # The only unsolicited letter we send. A mail client shows this as an
        # unsubscribe button, which keeps recipients from reaching for "spam".
        headers={"List-Unsubscribe": f"<mailto:{settings.EMAIL_CONTACT}?subject=unsubscribe>"},
    )


def send_brand_team_invite_email(
    *,
    to: str,
    brand_name: str,
    invite_url: str,
    site_url: str,
    role: str,
    reply_to: str | None = None,
    language: str | None = None,
) -> EmailSendResult:
    """Invite one exact email address to an existing manufacturer team."""
    subject = translate("brandTeamInvite.subject", language, brand_name=brand_name)
    html = _render(
        "brand_team_invite.html",
        language=language,
        subject=subject,
        brand_name=brand_name,
        invite_url=invite_url,
        site_url=site_url,
        role_label=translate(
            "brandTeamInvite.roleOwner" if role == "owner" else "brandTeamInvite.roleEditor",
            language,
        ),
    )
    return send_email_tracked(
        to=to,
        subject=subject,
        html=html,
        sender_profile="transactional",
        reply_to=reply_to,
    )
