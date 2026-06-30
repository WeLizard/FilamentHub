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


def send_brand_invite_email(
    *, to: str, brand_name: str | None, invite_url: str, site_url: str
) -> bool:
    """Send a pre-verified brand invitation to a manufacturer's corporate email."""
    subject = "Приглашение бренду на FilamentHub"
    brand_display = brand_name or "ваш бренд"
    contact_email = settings.EMAIL_FROM
    html = f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark light">
  <title>{subject}</title>
</head>
<body style="margin:0; padding:0; background:#0e0f13;">
  <div style="display:none; max-height:0; overflow:hidden; opacity:0; color:#0e0f13; font-size:1px; line-height:1px;">
    Ваши профили печати — в OrcaSlicer пользователя в один клик. Без обязательств.
  </div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0e0f13;">
    <tr>
      <td align="center" style="padding:28px 14px;">

        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px; max-width:100%; background:#14161d; border:1px solid #23262f; border-radius:16px; overflow:hidden;">

          <!-- Hero -->
          <tr>
            <td style="padding:0; line-height:0;">
              <img src="{site_url}/email/hero.jpg" width="600" alt="FilamentHub"
                   style="display:block; width:100%; height:auto; border:0;">
            </td>
          </tr>

          <!-- Контент -->
          <tr>
            <td style="padding:30px 34px 8px 34px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <div style="font-size:14px; font-weight:600; letter-spacing:0.3px; color:#a78bfa;">
                Filament<span style="color:#34d399;">Hub</span>
              </div>
              <h1 style="margin:14px 0 0 0; font-size:23px; line-height:1.3; font-weight:700; color:#f3f4f6;">
                Ваш филамент, который печатает из коробки
              </h1>
              <p style="margin:16px 0 0 0; font-size:15px; line-height:1.6; color:#c7ccd4;">
                Здравствуйте! Меня зовут Илья, я разработчик FilamentHub — каталога
                филаментов, где у каждого материала есть готовый профиль печати, который
                синхронизируется прямо в OrcaSlicer. Я приглашаю
                <span style="color:#f3f4f6; font-weight:600;">{brand_display}</span>
                добавить свои материалы.
              </p>
              <p style="margin:16px 0 0 0; font-size:15px; line-height:1.6; color:#c7ccd4;">
                Коротко, чем это может быть полезно вам:
              </p>
            </td>
          </tr>

          <!-- Пункты пользы -->
          <tr>
            <td style="padding:8px 34px 0 34px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr><td style="padding:14px 0; border-top:1px solid #23262f;">
                  <div style="font-size:15px; font-weight:600; color:#f3f4f6;">Печатает из коробки</div>
                  <div style="margin-top:4px; font-size:14px; line-height:1.55; color:#9aa0ab;">
                    Ваш официальный профиль приходит пользователю в OrcaSlicer в один клик —
                    меньше неудачных печатей, меньше обращений в поддержку.
                  </div>
                </td></tr>
                <tr><td style="padding:14px 0; border-top:1px solid #23262f;">
                  <div style="font-size:15px; font-weight:600; color:#f3f4f6;">QR на катушке → импорт за секунду</div>
                  <div style="margin-top:4px; font-size:14px; line-height:1.55; color:#9aa0ab;">
                    Покупатель сканирует код на коробке и сразу получает ваш материал с готовым профилем.
                  </div>
                </td></tr>
                <tr><td style="padding:14px 0; border-top:1px solid #23262f; border-bottom:1px solid #23262f;">
                  <div style="font-size:15px; font-weight:600; color:#f3f4f6;">Витрина там, где выбирают филамент</div>
                  <div style="margin-top:4px; font-size:14px; line-height:1.55; color:#9aa0ab;">
                    Страница бренда, ваши линейки и рекомендованные настройки — плюс аналитика
                    по тому, как используют ваши материалы.
                  </div>
                </td></tr>
              </table>
            </td>
          </tr>

          <!-- Ряд из 3 миниатюр -->
          <tr>
            <td style="padding:22px 28px 4px 28px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td width="33.33%" valign="top" style="padding:0 6px;">
                    <img src="{site_url}/email/catalog.jpg" width="172" alt="Каталог с профилями"
                         style="display:block; width:100%; height:auto; border:1px solid #23262f; border-radius:10px;">
                    <div style="margin-top:8px; font-size:12px; line-height:1.4; color:#9aa0ab; text-align:center;">Каталог с профилями</div>
                  </td>
                  <td width="33.33%" valign="top" style="padding:0 6px;">
                    <img src="{site_url}/email/import.jpg" width="172" alt="Импорт материалов"
                         style="display:block; width:100%; height:auto; border:1px solid #23262f; border-radius:10px;">
                    <div style="margin-top:8px; font-size:12px; line-height:1.4; color:#9aa0ab; text-align:center;">Импорт материалов</div>
                  </td>
                  <td width="33.33%" valign="top" style="padding:0 6px;">
                    <img src="{site_url}/email/scan.jpg" width="172" alt="QR на катушке"
                         style="display:block; width:100%; height:auto; border:1px solid #23262f; border-radius:10px;">
                    <div style="margin-top:8px; font-size:12px; line-height:1.4; color:#9aa0ab; text-align:center;">QR на катушке</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- CTA -->
          <tr>
            <td style="padding:24px 34px 6px 34px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0 0 18px 0; font-size:14px; line-height:1.6; color:#c7ccd4;">
                Это бесплатно и ни к чему не обязывает. Приглашение персональное — по нему
                {brand_display} сразу получает подтверждённый статус производителя.
              </p>
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td align="center" bgcolor="#7c3aed" style="border-radius:10px;">
                    <a href="{invite_url}" target="_blank"
                       style="display:inline-block; padding:13px 26px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; font-size:15px; font-weight:600; color:#ffffff; text-decoration:none; border-radius:10px;">
                      Принять приглашение
                    </a>
                  </td>
                  <td style="width:10px; font-size:0; line-height:0;">&nbsp;</td>
                  <td align="center" style="border:1px solid #3a3f4b; border-radius:10px;">
                    <a href="{site_url}" target="_blank"
                       style="display:inline-block; padding:13px 24px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; font-size:15px; font-weight:600; color:#c7ccd4; text-decoration:none; border-radius:10px;">
                      Заглянуть к нам
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:14px 0 0 0; font-size:12px; line-height:1.5; color:#6b7280;">
                Не открывается кнопка? Скопируйте ссылку:<br>
                <a href="{invite_url}" style="color:#a78bfa; word-break:break-all;">{invite_url}</a>
              </p>
            </td>
          </tr>

          <!-- Низкое давление + подпись -->
          <tr>
            <td style="padding:18px 34px 26px 34px; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0; font-size:13px; line-height:1.6; color:#9aa0ab;">
                Если сейчас не актуально — просто проигнорируйте это письмо, повторно беспокоить не будем.
              </p>
              <p style="margin:16px 0 0 0; font-size:14px; line-height:1.6; color:#c7ccd4;">
                — Илья, разработчик FilamentHub<br>
                <a href="{site_url}" style="color:#a78bfa; text-decoration:none;">{site_url}</a>
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:16px 34px 24px 34px; border-top:1px solid #23262f; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
              <p style="margin:0; font-size:12px; line-height:1.55; color:#6b7280;">
                Вы получили это письмо, потому что мы приглашаем {brand_display} в каталог FilamentHub.
                Если это ошибка — напишите нам на
                <a href="mailto:{contact_email}" style="color:#9aa0ab;">{contact_email}</a>.
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
