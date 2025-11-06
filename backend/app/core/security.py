"""Security utilities (JWT, password hashing)."""

import secrets
from datetime import datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

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
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем тип токена
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT refresh token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Проверяем тип токена
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


def generate_api_key() -> str:
    """Generate a random API key for OrcaSlicer integration."""
    return secrets.token_urlsafe(32)


def generate_email_verification_token(user_id: int, email: str) -> str:
    """Generate an email verification token."""
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "email_verification",
        "exp": datetime.utcnow() + timedelta(days=7),  # Токен действителен 7 дней
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
    payload = {
        "user_id": user_id,
        "email": email,
        "type": "password_reset",
        "exp": datetime.utcnow() + timedelta(hours=1),  # Токен действителен 1 час
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

