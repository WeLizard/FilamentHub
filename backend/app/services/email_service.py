"""Email sending service via Resend."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_RESEND_RECEIVING_URL = "https://api.resend.com/emails/receiving"
_RESEND_EMAIL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **context: object) -> str:
    """Render an email template from app/templates/email."""
    return _jinja_env.get_template(template_name).render(**context)


def _is_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


@dataclass(frozen=True)
class EmailSendResult:
    """Provider result kept explicit for admin delivery tracking."""

    sent: bool
    provider_message_id: str | None = None
    error: str | None = None

    def __bool__(self) -> bool:
        return self.sent


def _get_from(profile: str = "transactional") -> str:
    addresses = {
        "transactional": settings.EMAIL_FROM,
        "partnerships": settings.EMAIL_PARTNERSHIPS_FROM,
        "pr": settings.EMAIL_PR_FROM,
    }
    if profile not in addresses:
        raise ValueError(f"Unknown email sender profile: {profile}")
    return f"{settings.EMAIL_FROM_NAME} <{addresses[profile]}>"


def send_email(*, to: str, subject: str, html: str) -> bool:
    """Send a single email. Returns True on success, False if not configured or on error."""
    if not _is_configured():
        logger.warning("Email sending skipped: RESEND_API_KEY not configured")
        return False

    resend.api_key = settings.RESEND_API_KEY
    try:
        resend.Emails.send({
            "from": _get_from(),
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception:
        logger.error("Failed to send email to %s", to, exc_info=True)
        return False


def send_email_tracked(
    *,
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
    sender_profile: str = "transactional",
    reply_to: str | None = None,
    headers: dict[str, str] | None = None,
) -> EmailSendResult:
    """Send email and return a trackable provider result."""
    if not _is_configured():
        logger.warning("Email sending skipped: RESEND_API_KEY not configured")
        return EmailSendResult(sent=False, error="RESEND_API_KEY is not configured")

    try:
        from_address = _get_from(sender_profile)
    except ValueError as exc:
        return EmailSendResult(sent=False, error=str(exc))

    params: dict[str, object] = {
        "from": from_address,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        params["text"] = text
    if reply_to:
        params["reply_to"] = [reply_to]
    if headers:
        params["headers"] = headers

    resend.api_key = settings.RESEND_API_KEY
    try:
        response = resend.Emails.send(params)  # type: ignore[arg-type]
        provider_id = response.get("id") if isinstance(response, dict) else None
        return EmailSendResult(sent=True, provider_message_id=provider_id)
    except Exception as exc:
        logger.error("Failed to send tracked email to %s", to, exc_info=True)
        return EmailSendResult(sent=False, error=str(exc)[:500])


def get_email_sender(profile: str) -> str:
    """Return the configured sender identity for persistence and UI display."""
    return _get_from(profile)


def get_received_email(email_id: str) -> dict:
    """Retrieve full content for a verified Resend inbound event."""
    if not _is_configured():
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


def send_admin_reply_email(
    *,
    to: str,
    subject: str,
    body: str,
    sender_profile: str,
    reply_to: str | None,
    headers: dict[str, str] | None = None,
) -> EmailSendResult:
    """Send a safe plain-text authored reply using the shared email template."""
    html = _render(
        "admin_reply.html",
        subject=subject,
        body=body,
        contact_email=settings.EMAIL_CONTACT,
    )
    return send_email_tracked(
        to=to,
        subject=subject,
        html=html,
        text=body,
        sender_profile=sender_profile,
        reply_to=reply_to,
        headers=headers,
    )


def send_password_reset_email(*, to: str, reset_url: str) -> bool:
    """Send password reset link."""
    subject = "Восстановление пароля FilamentHub"
    html = _render("password_reset.html", subject=subject, reset_url=reset_url)
    return send_email(to=to, subject=subject, html=html)


def send_email_change_email(*, to: str, confirm_url: str) -> bool:
    """Send email change confirmation to the new address."""
    subject = "Подтвердите новый email — FilamentHub"
    html = _render("email_change.html", subject=subject, confirm_url=confirm_url)
    return send_email(to=to, subject=subject, html=html)


def send_brand_status_email(*, to: str, brand_name: str, approved: bool, reason: str | None = None) -> bool:
    """Send brand verification status notification."""
    subject = (
        f"Бренд «{brand_name}» подтверждён — FilamentHub"
        if approved
        else f"Заявка на бренд «{brand_name}» отклонена — FilamentHub"
    )
    html = _render(
        "brand_status.html",
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
) -> EmailSendResult:
    """Send a pre-verified brand invitation to a manufacturer's corporate email."""
    brand_display = brand_name or "ваш бренд"
    subject = (
        f"Приглашение официально представить {brand_name} в FilamentHub"
        if brand_name
        else "Приглашение официально представить бренд в FilamentHub"
    )
    html = _render(
        "brand_invite.html",
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
    )


def send_brand_team_invite_email(
    *,
    to: str,
    brand_name: str,
    invite_url: str,
    site_url: str,
    role: str,
    reply_to: str | None = None,
) -> EmailSendResult:
    """Invite one exact email address to an existing manufacturer team."""
    subject = f"Приглашение в команду {brand_name} в FilamentHub"
    html = _render(
        "brand_team_invite.html",
        subject=subject,
        brand_name=brand_name,
        invite_url=invite_url,
        site_url=site_url,
        role_label="владельца" if role == "owner" else "редактора",
    )
    return send_email_tracked(
        to=to,
        subject=subject,
        html=html,
        sender_profile="transactional",
        reply_to=reply_to,
    )
