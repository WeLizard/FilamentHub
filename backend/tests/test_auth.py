"""Tests for authentication endpoints."""

from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.brand import Brand
from app.models.user import User
from app.models.user_legal_acceptance import UserLegalAcceptance
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_PRIVACY_POLICY_VERSION,
    CURRENT_TERMS_VERSION,
    LEGAL_UPDATE_EFFECTIVE_DATE,
    LEGAL_UPDATE_NOTE,
)
from app.services.oauth_service import get_google_auth_url
from app.services.organization_access import grant_brand_owner_membership

LEGAL_REGISTRATION_FIELDS = {
    "terms_accepted": True,
    "personal_data_consent": True,
    "terms_version": CURRENT_TERMS_VERSION,
    "personal_data_consent_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    "privacy_policy_version": CURRENT_PRIVACY_POLICY_VERSION,
    "legal_language": "en",
}


def test_google_oauth_requests_only_basic_identity_without_offline_access(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "google-id")

    url = get_google_auth_url("state-token")

    assert url is not None
    query = parse_qs(urlparse(url).query)
    assert set(query["scope"][0].split()) == {"openid", "email", "profile"}
    assert "access_type" not in query


@pytest.mark.asyncio
async def test_auth_methods_are_server_authoritative(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setattr(settings, "YANDEX_CLIENT_ID", "yandex-id")
    monkeypatch.setattr(settings, "YANDEX_CLIENT_SECRET", "yandex-secret")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "recaptcha-secret")

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_ru")
    ru_response = await client.get("/api/v1/auth/methods")
    assert ru_response.status_code == 200
    assert ru_response.headers["Cache-Control"] == "private, no-store"
    assert ru_response.json() == {
        "access_region": "ru",
        "local_login": True,
        "local_registration": True,
        "oauth_providers": ["yandex"],
        "registration_captcha": None,
    }

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_intl")
    intl_response = await client.get("/api/v1/auth/methods")
    assert intl_response.status_code == 200
    assert intl_response.json() == {
        "access_region": "intl",
        "local_login": True,
        "local_registration": True,
        "oauth_providers": ["google", "yandex"],
        "registration_captcha": "recaptcha",
    }

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "geoip")
    monkeypatch.setattr(settings, "GEOIP_COUNTRY_DB_PATH", "missing-country.mmdb")
    unknown_response = await client.get("/api/v1/auth/methods")
    assert unknown_response.status_code == 200
    assert unknown_response.json() == {
        "access_region": "unknown",
        "local_login": True,
        "local_registration": True,
        "oauth_providers": ["yandex"],
        "registration_captcha": None,
    }


@pytest.mark.asyncio
async def test_oauth_provider_policy_is_enforced_on_direct_api_calls(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setattr(settings, "YANDEX_CLIENT_ID", "yandex-id")
    monkeypatch.setattr(settings, "YANDEX_CLIENT_SECRET", "yandex-secret")

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_ru")
    blocked_google = await client.get("/api/v1/auth/oauth/google/url")
    assert blocked_google.status_code == 403
    assert blocked_google.json()["detail"] == {
        "code": "ERR_OAUTH_PROVIDER_NOT_AVAILABLE",
        "params": {"provider": "google"},
    }

    blocked_google_callback = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "unused", "state": "unused"},
    )
    assert blocked_google_callback.status_code == 403
    assert blocked_google_callback.json()["detail"]["code"] == (
        "ERR_OAUTH_PROVIDER_NOT_AVAILABLE"
    )

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_intl")
    allowed_yandex = await client.get("/api/v1/auth/oauth/yandex/url")
    assert allowed_yandex.status_code == 200


@pytest.mark.asyncio
async def test_ru_registration_never_invokes_google_recaptcha(
    client: AsyncClient,
    monkeypatch,
):
    from app.core import utils as core_utils

    calls = 0

    async def rejected_recaptcha(token: str, remote_ip: str | None = None) -> bool:
        nonlocal calls
        calls += 1
        return False

    monkeypatch.setattr(core_utils, "verify_recaptcha", rejected_recaptcha)
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_ru")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET_KEY", "recaptcha-secret")

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "ru-no-recaptcha@example.com",
            "username": "ru_no_recaptcha",
            "password": "Password123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )

    assert response.status_code == 201
    assert calls == 0


@pytest.mark.asyncio
async def test_legal_requirements_are_public_and_versioned(
    client: AsyncClient,
    monkeypatch,
):
    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_intl")
    response = await client.get("/api/v1/auth/legal-requirements")

    assert response.status_code == 200
    assert response.json() == {
        "legal_pack": "intl",
        "edition_id": "global-2026-08-01",
        "terms_version": CURRENT_TERMS_VERSION,
        "personal_data_consent_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        "privacy_policy_version": CURRENT_PRIVACY_POLICY_VERSION,
        "terms_url": "/user-agreement?pack=intl&edition=global-2026-08-01",
        "personal_data_consent_url": (
            "/personal-data-consent?pack=intl&edition=global-2026-08-01"
        ),
        "privacy_policy_url": (
            "/privacy-policy?pack=intl&edition=global-2026-08-01"
        ),
        "legal_update_effective_date": LEGAL_UPDATE_EFFECTIVE_DATE.isoformat(),
        "legal_update_note": LEGAL_UPDATE_NOTE,
    }


@pytest.mark.asyncio
async def test_legal_document_is_public_and_pinned_to_an_edition(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/legal-documents/terms",
        params={
            "language": "ru",
            "pack": "ru",
            "edition": "global-2026-08-01",
        },
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    body = response.json()
    assert body["legal_pack"] == "ru"
    assert body["edition_id"] == "global-2026-08-01"
    assert body["document_type"] == "terms"
    assert body["language"] == "ru"
    assert body["title"] == "Пользовательское соглашение"
    assert body["revision_label"] == "Редакция от 1 августа 2026 года"
    assert "## 1. Предмет Соглашения" in body["markdown"]


@pytest.mark.asyncio
async def test_registration_requires_separate_current_legal_acceptance(
    client: AsyncClient,
):
    base = {
        "email": "legal-required@example.com",
        "username": "legal_required",
        "password": "testpassword123",
        "role": "user",
    }

    missing = await client.post("/api/v1/auth/register", json=base)
    assert missing.status_code == 422

    stale = await client.post(
        "/api/v1/auth/register",
        json={
            **base,
            **LEGAL_REGISTRATION_FIELDS,
            "terms_version": "stale",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "ERR_LEGAL_DOCUMENT_VERSION_MISMATCH"

    stale_privacy = await client.post(
        "/api/v1/auth/register",
        json={
            **base,
            **LEGAL_REGISTRATION_FIELDS,
            "privacy_policy_version": "stale",
        },
    )
    assert stale_privacy.status_code == 409
    assert (
        stale_privacy.json()["detail"]["code"]
        == "ERR_LEGAL_DOCUMENT_VERSION_MISMATCH"
    )


@pytest.mark.asyncio
async def test_registration_records_separate_legal_evidence(
    client: AsyncClient,
    db_session: AsyncSession,
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "legal-evidence@example.com",
            "username": "legal_evidence",
            "password": "testpassword123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )

    assert response.status_code == 201
    assert response.json()["legal_onboarding_required"] is False
    user = (
        await db_session.execute(
            select(User).where(User.email == "legal-evidence@example.com")
        )
    ).scalar_one()
    rows = (
        await db_session.execute(
            select(UserLegalAcceptance)
            .where(UserLegalAcceptance.user_id == user.id)
            .order_by(UserLegalAcceptance.document_type)
        )
    ).scalars().all()
    assert [row.document_type for row in rows] == [
        "personal_data_consent",
        "terms",
    ]
    assert {row.acceptance_source for row in rows} == {"registration"}
    assert {row.language for row in rows} == {"en"}
    assert {row.related_privacy_policy_version for row in rows} == {
        CURRENT_PRIVACY_POLICY_VERSION
    }
    assert user.privacy_policy_version_presented == CURRENT_PRIVACY_POLICY_VERSION


@pytest.mark.asyncio
async def test_existing_or_oauth_user_must_accept_before_private_features(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.core.security import create_access_token

    user = User(
        email="legal-onboarding@example.com",
        username="legal_onboarding",
        oauth_provider="google",
        oauth_provider_id="google-legal-1",
        active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    token = create_access_token({"sub": user.email, "user_id": user.id})
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["legal_onboarding_required"] is True

    blocked = await client.post(
        "/api/v1/auth/plugin-session",
        json={},
        headers=headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "ERR_LEGAL_ACCEPTANCE_REQUIRED"

    legacy_dependency_blocked = await client.get(
        "/api/v1/filament-reviews/my",
        headers=headers,
    )
    assert legacy_dependency_blocked.status_code == 403
    assert (
        legacy_dependency_blocked.json()["detail"]["code"]
        == "ERR_LEGAL_ACCEPTANCE_REQUIRED"
    )

    stale = await client.post(
        "/api/v1/auth/legal-acceptance",
        headers=headers,
        json={
            **LEGAL_REGISTRATION_FIELDS,
            "terms_version": "stale",
        },
    )
    assert stale.status_code == 409

    accepted = await client.post(
        "/api/v1/auth/legal-acceptance",
        headers=headers,
        json=LEGAL_REGISTRATION_FIELDS,
    )
    assert accepted.status_code == 200
    assert accepted.json()["legal_onboarding_required"] is False

    repeated = await client.post(
        "/api/v1/auth/legal-acceptance",
        headers=headers,
        json=LEGAL_REGISTRATION_FIELDS,
    )
    assert repeated.status_code == 200
    rows = (
        await db_session.execute(
            select(UserLegalAcceptance).where(
                UserLegalAcceptance.user_id == user.id
            )
        )
    ).scalars().all()
    assert len(rows) == 2

    unlocked = await client.post(
        "/api/v1/auth/plugin-session",
        json={},
        headers=headers,
    )
    assert unlocked.status_code == 200


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    user_data = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert "password" not in data  # Password should not be in response
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test registering with duplicate email."""
    user_data = {
        "email": "duplicate@example.com",
        "username": "user1",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    # First registration
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201

    # Try to register again with same email
    user_data["username"] = "user2"  # Different username
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test user login."""
    # Register first
    user_data = {
        "email": "login@example.com",
        "username": "loginuser",
        "password": "loginpassword123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    await client.post("/api/v1/auth/register", json=user_data)

    # Login
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"],
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["access_token"] is not None


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password."""
    # Register first
    user_data = {
        "email": "wrongpass@example.com",
        "username": "wrongpassuser",
        "password": "correctpassword123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    await client.post("/api/v1/auth/register", json=user_data)

    # Try to login with wrong password
    login_data = {
        "email": user_data["email"],
        "password": "wrongpassword",
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_oauth_only_user_can_set_local_password_via_reset(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Disabling an OAuth provider must not lock its existing users out."""
    from app.api.v1.endpoints import auth as auth_module

    user = User(
        email="oauth-reset@example.com",
        username="oauthreset",
        password_hash=None,
        oauth_provider="google",
        oauth_provider_id="google-reset-1",
        active=True,
        email_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    sent: dict[str, str] = {}

    def capture_reset_email(*, to: str, reset_url: str, language: str) -> bool:
        sent["to"] = to
        sent["reset_url"] = reset_url
        sent["language"] = language
        return True

    monkeypatch.setattr(auth_module, "send_password_reset_email", capture_reset_email)

    forgot = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user.email, "language": "zh"},
    )
    assert forgot.status_code == 200
    assert sent["to"] == user.email
    assert sent["language"] == "zh"

    reset_token = sent["reset_url"].rsplit("token=", 1)[1]
    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "new_password": "NewLocalPassword123!"},
    )
    assert reset.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "NewLocalPassword123!"},
    )
    assert login.status_code == 200
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """Test getting current user info."""
    # Register and login
    user_data = {
        "email": "currentuser@example.com",
        "username": "currentuser",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    await client.post("/api/v1/auth/register", json=user_data)

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    token = login_response.json()["access_token"]

    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]


@pytest.mark.asyncio
async def test_profile_update_cannot_assign_arbitrary_brand(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    """The generic profile endpoint must never grant or select brand access."""
    brand = Brand(name="Protected Brand", slug="protected-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await auth_client.patch("/api/v1/auth/me", json={"brand_id": brand.id})
    assert response.status_code == 200
    assert response.json()["brand_id"] is None
    await db_session.refresh(auth_user)
    assert auth_user.brand_id is None


@pytest.mark.asyncio
async def test_active_brand_requires_membership_and_lists_granted_brands(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """Active brand is a scoped workspace choice, not an authorization grant."""
    allowed = Brand(name="Allowed Brand", slug="allowed-brand", active=True, verified=True)
    denied = Brand(name="Denied Brand", slug="denied-brand", active=True, verified=True)
    db_session.add_all([allowed, denied])
    await db_session.flush()
    await grant_brand_owner_membership(
        db_session,
        brand=allowed,
        user=auth_user,
        granted_by_id=admin_user.id,
    )
    await db_session.commit()

    denied_response = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": denied.id},
    )
    assert denied_response.status_code == 403

    brands_response = await auth_client.get("/api/v1/auth/me/brands")
    assert brands_response.status_code == 200
    assert [item["brand_id"] for item in brands_response.json()] == [allowed.id]
    assert brands_response.json()[0]["membership_role"] == "owner"

    selected = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": allowed.id},
    )
    assert selected.status_code == 200
    assert selected.json()["brand_id"] == allowed.id

    cleared = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["brand_id"] is None


@pytest.mark.asyncio
async def test_admin_role_does_not_grant_company_workspace_access(
    admin_client: AsyncClient,
    admin_user: User,
    auth_user: User,
    db_session: AsyncSession,
):
    """Site admins moderate brands without implicitly joining their workspaces."""
    admin_brand = Brand(
        name="Admin Membership Brand",
        slug="admin-membership-brand",
        active=True,
        verified=True,
    )
    other_brand = Brand(
        name="Other Company Brand",
        slug="other-company-brand",
        active=True,
        verified=True,
    )
    db_session.add_all([admin_brand, other_brand])
    await db_session.flush()
    await grant_brand_owner_membership(
        db_session,
        brand=admin_brand,
        user=admin_user,
    )
    await grant_brand_owner_membership(
        db_session,
        brand=other_brand,
        user=auth_user,
        granted_by_id=admin_user.id,
    )
    await db_session.commit()

    brands_response = await admin_client.get("/api/v1/auth/me/brands")
    assert brands_response.status_code == 200
    assert [item["brand_id"] for item in brands_response.json()] == [admin_brand.id]
    assert brands_response.json()[0]["membership_role"] == "owner"

    denied_response = await admin_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": other_brand.id},
    )
    assert denied_response.status_code == 403
    await db_session.refresh(admin_user)
    assert admin_user.brand_id == admin_brand.id


@pytest.mark.asyncio
async def test_cookie_auth_login_and_me_in_dual_mode(client: AsyncClient, monkeypatch):
    """Cookie auth should work in dual mode without Authorization header."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "cookie-dual@example.com",
        "username": "cookie_dual_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    assert settings.AUTH_ACCESS_COOKIE_NAME in login_response.headers.get("set-cookie", "")

    me_response = await client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user_data["email"]


@pytest.mark.asyncio
async def test_cookie_auth_requires_csrf_for_mutation(client: AsyncClient, monkeypatch):
    """Mutating requests with cookie auth must provide matching CSRF header."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "csrf@example.com",
        "username": "csrf_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200

    no_csrf_response = await client.patch(
        "/api/v1/auth/me/settings",
        json={"allow_print_profiles_export": False},
    )
    assert no_csrf_response.status_code == 403

    csrf_token = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert csrf_token is not None

    with_csrf_response = await client.patch(
        "/api/v1/auth/me/settings",
        json={"allow_print_profiles_export": False},
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf_token},
    )
    assert with_csrf_response.status_code == 200
    assert with_csrf_response.json()["allow_print_profiles_export"] is False


@pytest.mark.asyncio
async def test_legacy_bearer_still_works_in_dual_mode(client: AsyncClient, monkeypatch):
    """Legacy Bearer flow must remain valid when dual mode is enabled."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "legacy-dual@example.com",
        "username": "legacy_dual_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user_data["email"]


@pytest.mark.asyncio
async def test_logout_revokes_legacy_access_token(client: AsyncClient):
    """After logout, previously issued access token should be rejected."""
    user_data = {
        "email": "revoke@example.com",
        "username": "revoke_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401


@pytest.mark.asyncio
async def test_cookie_refresh_requires_csrf_in_dual_mode(client: AsyncClient, monkeypatch):
    """Cookie refresh should reject request without CSRF token in dual mode."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "cookie-refresh-csrf@example.com",
        "username": "cookie_refresh_csrf_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200

    no_csrf_refresh = await client.post("/api/v1/auth/refresh")
    assert no_csrf_refresh.status_code == 403

    csrf_token = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert csrf_token is not None
    with_csrf_refresh = await client.post(
        "/api/v1/auth/refresh",
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf_token},
    )
    assert with_csrf_refresh.status_code == 200
    assert "access_token" in with_csrf_refresh.json()


@pytest.mark.asyncio
async def test_legacy_refresh_body_still_works_in_dual_mode(client: AsyncClient, monkeypatch):
    """Legacy refresh with body token must stay valid in dual mode."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "legacy-refresh@example.com",
        "username": "legacy_refresh_user",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]
    assert refresh_token

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()


@pytest.mark.asyncio
async def test_upload_avatar(client: AsyncClient, monkeypatch, tmp_path):
    """Avatar uploads are decoded, normalized to WebP and replace the old file."""
    import struct
    from io import BytesIO

    from PIL import Image

    from app.services import file_service

    monkeypatch.setattr(file_service, "get_upload_root_dir", lambda: tmp_path)
    user_data = {
        "email": "avatar@example.com",
        "username": "avataruser",
        "password": "password123",
        "role": "user",
        **LEGAL_REGISTRATION_FIELDS,
    }
    await client.post("/api/v1/auth/register", json=user_data)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    token = login.json()["access_token"]

    def png_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (640, 320), color).save(output, "PNG")
        return output.getvalue()

    def bmp_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (640, 320), color).save(output, "BMP")
        return output.getvalue()

    def oversized_bmp_bytes(width: int, height: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (1, 1), (0, 0, 0)).save(output, "BMP")
        data = bytearray(output.getvalue())
        struct.pack_into("<I", data, 18, width)
        struct.pack_into("<I", data, 22, height)
        return bytes(data)

    resp = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("a.bmp", bmp_bytes((255, 0, 0)), "image/bmp")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    first_url = resp.json().get("avatar_url") or ""
    assert first_url.startswith("/uploads/avatars/")
    assert first_url.endswith(".webp")
    first_path = tmp_path / "avatars" / first_url.rsplit("/", 1)[-1]
    assert first_path.exists()
    with Image.open(first_path) as stored:
        assert stored.format == "WEBP"
        assert stored.size == (256, 256)

    oversize = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("too-big.bmp", oversized_bmp_bytes(5001, 5000), "image/bmp")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert oversize.status_code == 400
    assert oversize.json()["detail"]["code"] == "ERR_FILE_SIZE_EXCEEDED"
    assert first_path.exists()

    disguised = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("payload.png", b"<script>alert(1)</script>", "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disguised.status_code == 400
    assert disguised.json()["detail"]["code"] == "ERR_FILE_CONTENT_MISMATCH"
    assert first_path.exists()

    replaced = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("b.png", png_bytes((0, 0, 255)), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replaced.status_code == 200
    second_url = replaced.json()["avatar_url"]
    second_path = tmp_path / "avatars" / second_url.rsplit("/", 1)[-1]
    assert second_path.exists()
    assert not first_path.exists()


@pytest.mark.asyncio
async def test_oauth_callback_validates_state(client: AsyncClient, monkeypatch):
    """OAuth callback must accept only the state issued to this browser (CSRF)."""
    from app.api.v1.endpoints import auth as auth_module
    from app.services.oauth_service import OAuthUserInfo

    monkeypatch.setattr(settings, "AUTH_REGION_MODE", "static_intl")
    monkeypatch.setattr(auth_module, "is_provider_configured", lambda provider: True)
    monkeypatch.setattr(
        auth_module,
        "get_google_auth_url",
        lambda state: f"https://accounts.google.com/o/oauth2/auth?state={state}",
    )

    async def fake_exchange(code: str) -> OAuthUserInfo:
        return OAuthUserInfo(
            provider="google",
            provider_id="g-123",
            email="oauth-state@example.com",
            name="OAuth User",
            email_verified=True,
        )

    monkeypatch.setattr(auth_module, "exchange_google_code", fake_exchange)

    # No state cookie at all -> rejected
    no_cookie = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": "forged-state"},
    )
    assert no_cookie.status_code == 401
    assert no_cookie.json()["detail"]["code"] == "ERR_OAUTH_INVALID_STATE"

    # Issue a real state (server sets the HttpOnly cookie on this client)
    url_resp = await client.get("/api/v1/auth/oauth/google/url")
    assert url_resp.status_code == 200
    issued_state = url_resp.json()["state"]

    # Cookie present but state forged -> rejected
    mismatch = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": "forged-state"},
    )
    assert mismatch.status_code == 401
    assert mismatch.json()["detail"]["code"] == "ERR_OAUTH_INVALID_STATE"

    # Matching state -> flow proceeds, user is created and logged in
    ok = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": issued_state},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    assert ok.json()["legal_onboarding_required"] is True


@pytest.mark.asyncio
async def test_plugin_session_is_short_lived_and_endpoint_scoped(
    auth_client: AsyncClient,
    auth_user,
):
    """Plugin capability must never become a replacement account access token."""
    from app.core.security import create_plugin_token, decode_plugin_token

    issued = await auth_client.post("/api/v1/auth/plugin-session", json={})
    assert issued.status_code == 200
    assert issued.headers["Cache-Control"] == "no-store"
    payload = issued.json()
    assert payload["expires_in"] == settings.PLUGIN_TOKEN_EXPIRE_MINUTES * 60
    assert "refresh_token" not in payload

    plugin_token = payload["plugin_token"]
    decoded = decode_plugin_token(plugin_token)
    assert decoded is not None
    assert decoded["user_id"] == auth_user.id
    assert set(decoded["scopes"]) == {"presets:read", "presets:write"}
    plugin_headers = {"Authorization": f"Bearer {plugin_token}"}

    regular_api = await auth_client.get("/api/v1/auth/me", headers=plugin_headers)
    assert regular_api.status_code == 401

    plugin_read = await auth_client.get(
        "/api/v1/auth/my-presets",
        headers=plugin_headers,
    )
    assert plugin_read.status_code == 200

    plugin_write = await auth_client.post(
        "/api/v1/orcaslicer/filaments/import",
        headers=plugin_headers,
        json={"profiles": []},
    )
    assert plugin_write.status_code == 200

    read_only_token = create_plugin_token(
        {"sub": auth_user.email, "user_id": auth_user.id},
        ["presets:read"],
    )
    denied_write = await auth_client.post(
        "/api/v1/orcaslicer/filaments/import",
        headers={"Authorization": f"Bearer {read_only_token}"},
        json={"profiles": []},
    )
    assert denied_write.status_code == 403
    assert denied_write.json()["detail"]["code"] == "ERR_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_password_reset_finds_the_account_whatever_case_was_typed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """A mailbox is one account regardless of how the address is capitalised."""
    from app.api.v1.endpoints import auth as auth_module

    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "Mixed.Case@Example.com",
            "username": "mixed_case_user",
            "password": "Password123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )
    assert registration.status_code == 201

    stored = await db_session.scalar(
        select(User).where(User.username == "mixed_case_user")
    )
    assert stored is not None
    # The validator lowercases the domain, the local part is kept as typed;
    # only matching ignores case.
    assert stored.email == "Mixed.Case@example.com"

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "MIXED.CASE@example.com",
            "username": "duplicate_user",
            "password": "Password123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "ERR_EMAIL_EXISTS"

    sent: dict[str, str] = {}

    def capture_reset_email(*, to: str, reset_url: str, language: str) -> bool:
        sent["to"] = to
        return True

    monkeypatch.setattr(auth_module, "send_password_reset_email", capture_reset_email)
    forgot = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "mIxEd.cAsE@ExAmPlE.com"},
    )

    assert forgot.status_code == 200
    assert sent["to"] == "Mixed.Case@example.com"


@pytest.mark.asyncio
async def test_registration_sends_a_confirmation_the_owner_can_also_disown(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Soft confirmation: the account works at once, the address owner still has a way out."""
    from app.api.v1.endpoints import auth as auth_module

    sent: dict[str, str] = {}

    def capture(*, to: str, verify_url: str, reject_url: str, language: str) -> bool:
        sent["to"] = to
        sent["url"] = verify_url
        sent["reject"] = reject_url
        return True

    monkeypatch.setattr(auth_module, "send_email_verification_email", capture)
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "stranger@example.com",
            "username": "stranger_account",
            "password": "Password123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )

    assert registration.status_code == 201
    assert sent["to"] == "stranger@example.com"
    # The account is usable straight away; confirmation only records the address.
    assert registration.json()["email_verified"] is False

    token = sent["url"].rsplit("token=", 1)[1]
    disown = await client.post(f"/api/v1/auth/reject-registration?token={token}")
    assert disown.status_code == 200
    assert await db_session.scalar(
        select(User).where(User.username == "stranger_account")
    ) is None


@pytest.mark.asyncio
async def test_a_confirmed_account_cannot_be_removed_by_the_same_link(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    from app.api.v1.endpoints import auth as auth_module

    sent: dict[str, str] = {}

    def capture(*, to: str, verify_url: str, reject_url: str, language: str) -> bool:
        sent["url"] = verify_url
        return True

    monkeypatch.setattr(auth_module, "send_email_verification_email", capture)
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "real.owner@example.com",
            "username": "real_owner",
            "password": "Password123",
            "role": "user",
            **LEGAL_REGISTRATION_FIELDS,
        },
    )
    token = sent["url"].rsplit("token=", 1)[1]

    confirmed = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert confirmed.status_code == 200

    disown = await client.post(f"/api/v1/auth/reject-registration?token={token}")
    assert disown.status_code == 400
    assert await db_session.scalar(
        select(User).where(User.username == "real_owner")
    ) is not None
