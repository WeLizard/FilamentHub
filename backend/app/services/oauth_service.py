"""OAuth 2.0 service for Google and Yandex authentication."""

import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Provider configs ─────────────────────────────────────────────────

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = "openid email profile"

YANDEX_AUTH_URL = "https://oauth.yandex.ru/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.ru/token"
YANDEX_USERINFO_URL = "https://login.yandex.ru/info"
YANDEX_SCOPES = "login:email login:info"

OAUTH_CALLBACK_BASE_PATH = "/oauth/callback"

HTTP_TIMEOUT = 10.0


# ── Data classes ─────────────────────────────────────────────────────

class OAuthUserInfo:
    """Normalized user info from OAuth provider."""

    __slots__ = ("provider", "provider_id", "email", "name", "email_verified")

    def __init__(
        self,
        provider: str,
        provider_id: str,
        email: str,
        name: str | None = None,
        email_verified: bool = False,
    ):
        self.provider = provider
        self.provider_id = provider_id
        self.email = email
        self.name = name
        self.email_verified = email_verified


# ── State management ─────────────────────────────────────────────────

def generate_oauth_state() -> str:
    """Generate a cryptographic state parameter for CSRF protection."""
    return secrets.token_urlsafe(32)


def _build_redirect_uri(provider: str) -> str:
    """Build the OAuth callback redirect URI for the given provider."""
    return f"{settings.BASE_URL}{OAUTH_CALLBACK_BASE_PATH}/{provider}"


# ── Auth URL builders ────────────────────────────────────────────────

def get_google_auth_url(state: str) -> str | None:
    """Build Google OAuth authorization URL. Returns None if not configured."""
    if not settings.GOOGLE_CLIENT_ID:
        return None

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _build_redirect_uri("google"),
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def get_yandex_auth_url(state: str) -> str | None:
    """Build Yandex OAuth authorization URL. Returns None if not configured."""
    if not settings.YANDEX_CLIENT_ID:
        return None

    params = {
        "client_id": settings.YANDEX_CLIENT_ID,
        "redirect_uri": _build_redirect_uri("yandex"),
        "response_type": "code",
        "state": state,
        "force_confirm": "yes",
    }
    return f"{YANDEX_AUTH_URL}?{urlencode(params)}"


# ── Token exchange ───────────────────────────────────────────────────

async def exchange_google_code(code: str) -> OAuthUserInfo:
    """Exchange Google authorization code for user info."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        # Exchange code for tokens
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": _build_redirect_uri("google"),
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Fetch user info
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

    email = info.get("email", "")
    if not email:
        raise ValueError("Google account has no email")

    return OAuthUserInfo(
        provider="google",
        provider_id=str(info["id"]),
        email=email,
        name=info.get("name"),
        email_verified=info.get("verified_email", False),
    )


async def exchange_yandex_code(code: str) -> OAuthUserInfo:
    """Exchange Yandex authorization code for user info."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        # Exchange code for tokens
        token_resp = await client.post(
            YANDEX_TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.YANDEX_CLIENT_ID,
                "client_secret": settings.YANDEX_CLIENT_SECRET,
                "redirect_uri": _build_redirect_uri("yandex"),
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        tokens = token_resp.json()

        # Fetch user info
        userinfo_resp = await client.get(
            YANDEX_USERINFO_URL,
            headers={"Authorization": f"OAuth {tokens['access_token']}"},
            params={"format": "json"},
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

    email = info.get("default_email", "")
    if not email:
        raise ValueError("Yandex account has no email")

    display_name = info.get("display_name") or info.get("real_name")
    if not display_name:
        first = info.get("first_name", "")
        last = info.get("last_name", "")
        display_name = f"{first} {last}".strip() or None

    return OAuthUserInfo(
        provider="yandex",
        provider_id=str(info["id"]),
        email=email,
        name=display_name,
        email_verified=True,  # Yandex emails are always verified
    )


# ── Helpers ──────────────────────────────────────────────────────────

def generate_username_from_email(email: str) -> str:
    """Generate a username candidate from email address."""
    local_part = email.split("@")[0]
    # Keep only alphanumeric and underscores, limit length
    cleaned = "".join(c if c.isalnum() or c == "_" else "" for c in local_part)[:20]
    if not cleaned or len(cleaned) < 3:
        cleaned = "user"
    # Add short hash suffix to reduce collisions
    suffix = hashlib.md5(email.encode()).hexdigest()[:4]
    return f"{cleaned}_{suffix}"


def is_provider_configured(provider: str) -> bool:
    """Check if an OAuth provider is configured."""
    if provider == "google":
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    if provider == "yandex":
        return bool(settings.YANDEX_CLIENT_ID and settings.YANDEX_CLIENT_SECRET)
    return False
