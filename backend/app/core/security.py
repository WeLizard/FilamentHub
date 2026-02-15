"""Security utilities (JWT, password hashing)."""

import calendar
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

# Algorithm for JWT
ALGORITHM = settings.ALGORITHM

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__ident="2b")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    expire_timestamp = calendar.timegm(expire.utctimetuple())
    to_encode.update({"exp": expire_timestamp, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    expire_timestamp = calendar.timegm(expire.utctimetuple())
    to_encode.update({"exp": expire_timestamp, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            leeway=60,  # 60 seconds clock skew tolerance
        )

        # Check token type
        if payload.get("type") != "access":
            logger.warning("JWT token type mismatch: expected 'access', got '%s'", payload.get("type"))
            return None

        logger.debug("JWT token validated: user_id=%s", payload.get("user_id"))
        return payload
    except ExpiredSignatureError:
        logger.debug("JWT access token expired")
        return None
    except InvalidTokenError as e:
        logger.warning("JWT token validation failed: %s", str(e))
        return None
    except Exception as e:
        logger.error("Unexpected error decoding JWT token: %s", str(e), exc_info=True)
        return None


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT refresh token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            logger.warning("JWT refresh token type mismatch: expected 'refresh', got '%s'", payload.get("type"))
            return None
        return payload
    except ExpiredSignatureError:
        logger.debug("JWT refresh token expired")
        return None
    except InvalidTokenError as e:
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
    expire = datetime.now(timezone.utc) + timedelta(days=7)
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
        if payload.get("type") != "email_verification":
            return None
        return payload
    except InvalidTokenError:
        return None


def generate_password_reset_token(user_id: int, email: str) -> str:
    """Generate a password reset token."""
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
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
        if payload.get("type") != "password_reset":
            return None
        return payload
    except InvalidTokenError:
        return None
