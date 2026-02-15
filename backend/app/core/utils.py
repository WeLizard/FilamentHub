"""Общие утилиты для бэкенда."""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_recaptcha(token: str) -> bool:
    """Проверить reCAPTCHA v3 токен через Google API.

    Возвращает True если проверка пройдена (score >= threshold).
    Если RECAPTCHA_SECRET_KEY не настроен — пропускает проверку (для разработки).
    """
    if not settings.RECAPTCHA_SECRET_KEY:
        logger.warning("RECAPTCHA_SECRET_KEY not configured — skipping verification")
        return True

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://www.google.com/recaptcha/api/siteverify",
                data={
                    "secret": settings.RECAPTCHA_SECRET_KEY,
                    "response": token,
                },
            )
            result = resp.json()
    except Exception:
        logger.exception("reCAPTCHA verification request failed")
        # При ошибке сети не блокируем регистрацию
        return True

    if not result.get("success"):
        logger.warning("reCAPTCHA verification failed: %s", result.get("error-codes"))
        return False

    score = result.get("score", 0.0)
    if score < settings.RECAPTCHA_SCORE_THRESHOLD:
        logger.warning("reCAPTCHA score too low: %.2f (threshold: %.2f)", score, settings.RECAPTCHA_SCORE_THRESHOLD)
        return False

    return True


def escape_like(value: str) -> str:
    """Экранирует спецсимволы SQL LIKE/ILIKE (%, _, \\) в пользовательском вводе."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(value: str) -> str:
    """Формирует безопасный ILIKE-паттерн %value% с экранированием."""
    return f"%{escape_like(value)}%"
