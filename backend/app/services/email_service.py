"""Email sending service via Resend."""

import logging
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, **context: object) -> str:
    """Render an email template from app/templates/email."""
    return _jinja_env.get_template(template_name).render(**context)


def _is_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


def _get_from() -> str:
    return f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"


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


def send_brand_invite_email(*, to: str, brand_name: str | None, invite_url: str, site_url: str) -> bool:
    """Send a pre-verified brand invitation to a manufacturer's corporate email."""
    subject = "Приглашение бренду на FilamentHub"
    html = _render(
        "brand_invite.html",
        subject=subject,
        brand_display=brand_name or "ваш бренд",
        invite_url=invite_url,
        site_url=site_url,
        contact_email=settings.EMAIL_FROM,
    )
    return send_email(to=to, subject=subject, html=html)
