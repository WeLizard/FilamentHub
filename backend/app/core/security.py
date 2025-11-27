"""Security utilities (JWT, password hashing)."""

import calendar
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, ExpiredSignatureError, jwt
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

# Algorithm for JWT
ALGORITHM = settings.ALGORITHM

# Password hashing context
# Отключаем wrap bug detection для совместимости с bcrypt 4.x
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__ident="2b")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    try:
        return pwd_context.hash(password)
    except Exception as e:
        # Логируем ошибку для отладки
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error hashing password: {str(e)}", exc_info=True)
        raise


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    
    # ВАЖНО: Используем timezone.utc для правильной работы с UTC временем
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # ВАЖНО: JWT exp должен быть timestamp (int) в UTC
    # Используем calendar.timegm для правильной конвертации UTC datetime в timestamp
    # Это гарантирует, что timestamp будет правильным независимо от часового пояса системы
    expire_timestamp = calendar.timegm(expire.utctimetuple())
    to_encode.update({"exp": expire_timestamp, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    # ВАЖНО: JWT exp должен быть timestamp (int) в UTC
    expire_timestamp = calendar.timegm(expire.utctimetuple())
    to_encode.update({"exp": expire_timestamp, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT access token."""
    # ДИАГНОСТИКА: Декодируем токен без проверки подписи для просмотра содержимого
    try:
        unverified_payload = jwt.decode(token, key="", options={"verify_signature": False, "verify_exp": False})
        exp_timestamp = unverified_payload.get("exp")
        current_timestamp = calendar.timegm(datetime.now(timezone.utc).utctimetuple())
        
        if exp_timestamp:
            time_until_expiry = exp_timestamp - current_timestamp
            logger.info(
                "JWT token diagnostics: exp=%d (UTC timestamp), current=%d (UTC timestamp), "
                "time_until_expiry=%d seconds (%d minutes, %d hours, %d days)",
                exp_timestamp,
                current_timestamp,
                time_until_expiry,
                time_until_expiry // 60,
                time_until_expiry // 3600,
                time_until_expiry // 86400
            )
        else:
            logger.warning("JWT token has no 'exp' claim!")
    except Exception as e:
        logger.warning("Failed to decode JWT token for diagnostics: %s", str(e))
    
    # Теперь декодируем с проверкой подписи и exp
    try:
        # ВАЖНО: Добавляем leeway=60 секунд для учета расхождения времени (clock skew)
        # Это позволит токену быть валидным даже если время сервера и клиента отличаются на минуту
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"leeway": 60}  # 60 секунд допустимого расхождения времени
        )
        
        # Проверяем тип токена
        if payload.get("type") != "access":
            logger.warning("JWT token type mismatch: expected 'access', got '%s'", payload.get("type"))
            return None
        
        logger.debug("JWT token validated successfully: user_id=%s, email=%s", 
                    payload.get("user_id"), payload.get("sub"))
        return payload
    except ExpiredSignatureError as e:
        # ДИАГНОСТИКА: Показываем подробную информацию об истекшем токене
        try:
            unverified_payload = jwt.decode(token, key="", options={"verify_signature": False, "verify_exp": False})
            exp_timestamp = unverified_payload.get("exp")
            current_timestamp = calendar.timegm(datetime.now(timezone.utc).utctimetuple())
            
            if exp_timestamp:
                time_since_expiry = current_timestamp - exp_timestamp
                logger.warning(
                    "JWT token expired: exp=%d (UTC timestamp), current=%d (UTC timestamp), "
                    "expired %d seconds ago (%d minutes, %d hours, %d days ago). Error: %s",
                    exp_timestamp,
                    current_timestamp,
                    time_since_expiry,
                    time_since_expiry // 60,
                    time_since_expiry // 3600,
                    time_since_expiry // 86400,
                    str(e)
                )
            else:
                logger.warning("JWT token expired (no exp claim found). Error: %s", str(e))
        except Exception:
            pass  # Не критично, если не удалось декодировать для диагностики
        
        logger.warning("JWT token expired: %s", str(e))
        return None
    except JWTError as e:
        logger.warning("JWT token validation failed: %s (error type: %s)", str(e), type(e).__name__)
        return None
    except Exception as e:
        logger.error("Unexpected error decoding JWT token: %s", str(e), exc_info=True)
        return None


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT refresh token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем тип токена
        if payload.get("type") != "refresh":
            logger.warning("JWT refresh token type mismatch: expected 'refresh', got '%s'", payload.get("type"))
            return None
        return payload
    except ExpiredSignatureError:
        logger.warning("JWT refresh token expired")
        return None
    except JWTError as e:
        logger.warning("JWT refresh token validation failed: %s", str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error decoding JWT refresh token: %s", str(e), exc_info=True)
        return None


def generate_api_key() -> str:
    """Generate a random API key for OrcaSlicer integration."""
    return secrets.token_urlsafe(32)


def generate_email_verification_token(user_id: int, email: str) -> str:
    """Generate an email verification token."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)  # Токен действителен 7 дней
    expire_timestamp = calendar.timegm(expire.utctimetuple())
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "email_verification",
        "exp": expire_timestamp,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_email_verification_token(token: str) -> dict[str, Any] | None:
    """Decode an email verification token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем тип токена
        if payload.get("type") != "email_verification":
            return None
        return payload
    except JWTError:
        return None


def generate_password_reset_token(user_id: int, email: str) -> str:
    """Generate a password reset token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)  # Токен действителен 1 час
    expire_timestamp = calendar.timegm(expire.utctimetuple())
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "password_reset",
        "exp": expire_timestamp,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    """Decode a password reset token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем тип токена
        if payload.get("type") != "password_reset":
            return None
        return payload
    except JWTError:
        return None

