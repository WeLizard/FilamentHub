"""Global 'calculator free for everyone' promo toggle + effective access check.

The promo flag is stored in a JSON file on the uploads volume (shared across workers),
the same pattern as maintenance mode.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

CALCULATOR_PROMO_FILE = Path("/app/uploads/.calculator_promo.json")


def get_calculator_promo() -> bool:
    """Whether the calculator is currently free for everyone (admin promo)."""
    try:
        if CALCULATOR_PROMO_FILE.exists():
            with open(CALCULATOR_PROMO_FILE, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("enabled", False))
    except Exception:
        logger.warning("Failed to read calculator promo file", exc_info=True)
    return False


def set_calculator_promo(enabled: bool) -> None:
    """Enable/disable the global calculator promo (free for everyone)."""
    try:
        CALCULATOR_PROMO_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CALCULATOR_PROMO_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled}, f, ensure_ascii=False)
    except Exception:
        logger.warning("Failed to write calculator promo file", exc_info=True)


def user_has_calculator_access(user: User) -> bool:
    """Effective calculator (Pro) access: admins always, global promo, or a valid per-user grant."""
    if user.role == UserRole.ADMIN:
        return True
    if get_calculator_promo():
        return True
    if user.pro_access:
        return user.pro_expires_at is None or user.pro_expires_at > datetime.now(timezone.utc)
    return False
