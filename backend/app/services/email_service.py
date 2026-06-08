"""Email sending service via Resend."""

import logging

import resend

from app.core.config import settings

logger = logging.getLogger(__name__)


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
    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:16px;border:1px solid rgba(255,255,255,0.1);overflow:hidden;">
          <!-- Header -->
          <tr>
            <td style="padding:32px;text-align:center;background:linear-gradient(135deg,#7c3aed,#db2777);">
              <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">FilamentHub</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 16px;color:#f1f5f9;font-size:20px;">Восстановление пароля</h2>
              <p style="margin:0 0 24px;color:#94a3b8;line-height:1.6;">
                Мы получили запрос на восстановление пароля для вашего аккаунта.
                Нажмите кнопку ниже, чтобы задать новый пароль.
              </p>
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#7c3aed,#db2777);border-radius:10px;">
                    <a href="{reset_url}" style="display:inline-block;padding:14px 32px;color:#fff;font-weight:600;font-size:15px;text-decoration:none;">
                      Сбросить пароль
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;color:#64748b;font-size:13px;">
                Ссылка действительна 1 час. Если вы не запрашивали сброс пароля — просто проигнорируйте это письмо.
              </p>
              <p style="margin:0;color:#475569;font-size:12px;word-break:break-all;">
                {reset_url}
              </p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.08);text-align:center;">
              <p style="margin:0;color:#475569;font-size:12px;">
                © FilamentHub · <a href="https://filamenthub.ru" style="color:#7c3aed;text-decoration:none;">filamenthub.ru</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return send_email(to=to, subject=subject, html=html)


def send_email_change_email(*, to: str, confirm_url: str) -> bool:
    """Send email change confirmation to the new address."""
    subject = "Подтвердите новый email — FilamentHub"
    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:16px;border:1px solid rgba(255,255,255,0.1);overflow:hidden;">
          <tr>
            <td style="padding:32px;text-align:center;background:linear-gradient(135deg,#7c3aed,#db2777);">
              <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">FilamentHub</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <h2 style="margin:0 0 16px;color:#f1f5f9;font-size:20px;">Подтверждение нового email</h2>
              <p style="margin:0 0 24px;color:#94a3b8;line-height:1.6;">
                Вы запросили смену email-адреса в FilamentHub.
                Нажмите кнопку ниже, чтобы подтвердить этот адрес.
              </p>
              <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
                <tr>
                  <td style="background:linear-gradient(135deg,#7c3aed,#db2777);border-radius:10px;">
                    <a href="{confirm_url}" style="display:inline-block;padding:14px 32px;color:#fff;font-weight:600;font-size:15px;text-decoration:none;">
                      Подтвердить email
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;color:#64748b;font-size:13px;">
                Ссылка действительна 24 часа. Если вы не запрашивали смену email — проигнорируйте это письмо.
              </p>
              <p style="margin:0;color:#475569;font-size:12px;word-break:break-all;">
                {confirm_url}
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.08);text-align:center;">
              <p style="margin:0;color:#475569;font-size:12px;">
                © FilamentHub · <a href="https://filamenthub.ru" style="color:#7c3aed;text-decoration:none;">filamenthub.ru</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return send_email(to=to, subject=subject, html=html)


def send_brand_status_email(*, to: str, brand_name: str, approved: bool, reason: str | None = None) -> bool:
    """Send brand verification status notification."""
    if approved:
        subject = f"Бренд «{brand_name}» подтверждён — FilamentHub"
        status_text = "одобрена"
        color = "#22c55e"
        message = "Поздравляем! Ваша заявка на представительство бренда была одобрена администрацией."
        extra = ""
    else:
        subject = f"Заявка на бренд «{brand_name}» отклонена — FilamentHub"
        status_text = "отклонена"
        color = "#ef4444"
        message = "К сожалению, ваша заявка на представительство бренда была отклонена."
        extra = f'<p style="margin:16px 0 0;color:#94a3b8;font-size:14px;">Причина: {reason}</p>' if reason else ""

    html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#0f172a;font-family:system-ui,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:16px;border:1px solid rgba(255,255,255,0.1);overflow:hidden;">
          <tr>
            <td style="padding:32px;text-align:center;background:linear-gradient(135deg,#7c3aed,#db2777);">
              <h1 style="margin:0;color:#fff;font-size:24px;font-weight:700;">FilamentHub</h1>
            </td>
          </tr>
          <tr>
            <td style="padding:32px;">
              <div style="display:inline-block;padding:6px 14px;background:{color}22;border:1px solid {color}66;border-radius:20px;color:{color};font-size:13px;font-weight:600;margin-bottom:16px;">
                Заявка {status_text}
              </div>
              <h2 style="margin:0 0 8px;color:#f1f5f9;font-size:20px;">Бренд «{brand_name}»</h2>
              <p style="margin:0 0 0;color:#94a3b8;line-height:1.6;">{message}</p>
              {extra}
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px;border-top:1px solid rgba(255,255,255,0.08);text-align:center;">
              <p style="margin:0;color:#475569;font-size:12px;">
                © FilamentHub · <a href="https://filamenthub.ru" style="color:#7c3aed;text-decoration:none;">filamenthub.ru</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return send_email(to=to, subject=subject, html=html)
