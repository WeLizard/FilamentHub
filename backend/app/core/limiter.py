"""Rate limiting setup."""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Создаём глобальный limiter для использования в роутерах
limiter = Limiter(key_func=get_remote_address)

