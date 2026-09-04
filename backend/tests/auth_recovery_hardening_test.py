"""Credential-boundary and durable account-recovery regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.password_hashing import hash_password
from app.core.security import create_access_token, token_fingerprint
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.services.account_auth_service import token_data_for_user
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)
from app.services.refresh_session_service import issue_refresh_session

OLD_PASSWORD = "OldPassword123!"
NEW_PASSWORD = "NewPassword456!"


async def _create_user(
    db: AsyncSession,
    *,
    email: str,
    username: str,
    password: str | None = OLD_PASSWORD,
    role: UserRole = UserRole.USER,
    oauth: bool = False,
) -> User:
    user = User(
        email=email,
        username=username,
        password_hash=await hash_password(password) if password else None,
        oauth_provider="google" if oauth else None,
        oauth_provider_id=f"google-{username}" if oauth else None,
        role=role,
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _tokens(
    db: AsyncSession,
    user: User,
    *,
    refresh_families: int = 1,
) -> tuple[str, list[str]]:
    claims = token_data_for_user(user)
    access_token = create_access_token(claims)
    refresh_tokens = [
        await issue_refresh_session(db, user_id=user.id, token_data=claims)
        for _ in range(refresh_families)
    ]
    await db.commit()
    return access_token, refresh_tokens


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_general_profile_patch_cannot_change_password_or_profile_atomically(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(
        db_session,
        email="profile-password-boundary@example.com",
        username="profile_password_boundary",
    )
    access_token, _ = await _tokens(db_session, user)
    original_hash = user.password_hash

    response = await client.patch(
        "/api/v1/auth/me",
        json={"password": NEW_PASSWORD, "full_name": "Must not be applied"},
        headers=_bearer(access_token),
    )

    assert response.status_code == 401
    assert NEW_PASSWORD not in response.text
    await db_session.refresh(user)
    assert user.password_hash == original_hash
    assert user.full_name is None
    assert user.auth_version == 0


@pytest.mark.asyncio
async def test_password_change_requires_reauthentication_and_revokes_every_session(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(
        db_session,
        email="password-change@example.com",
        username="password_change",
    )
    old_access, old_refresh_tokens = await _tokens(
        db_session,
        user,
        refresh_families=2,
    )

    missing = await client.patch(
        "/api/v1/auth/me/password",
        json={"new_password": NEW_PASSWORD},
        headers=_bearer(old_access),
    )
    wrong = await client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": "WrongPassword999!", "new_password": NEW_PASSWORD},
        headers=_bearer(old_access),
    )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 200

    changed = await client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=_bearer(old_access),
    )
    assert changed.status_code == 200, changed.text

    await db_session.refresh(user)
    assert user.auth_version == 1
    sessions = (
        await db_session.scalars(
            select(RefreshSession).where(RefreshSession.user_id == user.id)
        )
    ).all()
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)
    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 401
    for refresh_token in old_refresh_tokens:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401

    old_login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": OLD_PASSWORD},
    )
    new_login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": NEW_PASSWORD},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_oauth_only_account_can_set_first_password_and_invalidates_old_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(
        db_session,
        email="oauth-first-password@example.com",
        username="oauth_first_password",
        password=None,
        oauth=True,
    )
    old_access, old_refresh_tokens = await _tokens(db_session, user)

    changed = await client.patch(
        "/api/v1/auth/me/password",
        json={"new_password": NEW_PASSWORD},
        headers=_bearer(old_access),
    )

    assert changed.status_code == 200, changed.text
    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_tokens[0]},
        )
    ).status_code == 401
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": NEW_PASSWORD},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_is_durable_one_time_and_revokes_sibling_grants_and_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1.endpoints import auth as auth_endpoint

    user = await _create_user(
        db_session,
        email="durable-reset@example.com",
        username="durable_reset",
    )
    old_access, old_refresh_tokens = await _tokens(
        db_session,
        user,
        refresh_families=2,
    )
    reset_tokens: list[str] = []

    def capture_email(*, to: str, reset_url: str, language: str) -> bool:
        assert to == user.email
        reset_tokens.append(reset_url.rsplit("token=", 1)[1])
        return True

    monkeypatch.setattr(auth_endpoint, "send_password_reset_email", capture_email)
    for _ in range(2):
        forgot = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user.email, "language": "en"},
        )
        assert forgot.status_code == 200
    assert len(reset_tokens) == 2

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tokens[0], "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 200, reset.text
    replay = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tokens[0], "new_password": "ReplayPassword789!"},
    )
    sibling = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_tokens[1], "new_password": "SiblingPassword789!"},
    )
    assert replay.status_code == 400
    assert sibling.status_code == 400

    grants = (
        await db_session.scalars(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
    ).all()
    assert len(grants) == 2
    assert all(grant.consumed_at is not None for grant in grants)
    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 401
    for refresh_token in old_refresh_tokens:
        assert (
            await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh_token},
            )
        ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": OLD_PASSWORD},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": NEW_PASSWORD},
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_forgot_password_grant_failure_stays_generic_after_rollback(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1.endpoints import auth as auth_endpoint

    user = await _create_user(
        db_session,
        email="failed-reset-grant@example.com",
        username="failed_reset_grant",
    )
    ordinary = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "missing-reset-account@example.com", "language": "en"},
    )
    sent: list[str] = []

    async def fail_grant(*_args, **_kwargs) -> str:
        raise RuntimeError("reset grant storage unavailable")

    def capture_email(*, to: str, reset_url: str, language: str) -> bool:
        sent.append(to)
        return True

    monkeypatch.setattr(auth_endpoint, "issue_password_reset_grant", fail_grant)
    monkeypatch.setattr(auth_endpoint, "send_password_reset_email", capture_email)

    failed = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": user.email, "language": "en"},
    )

    assert failed.status_code == ordinary.status_code == 200
    assert failed.json() == ordinary.json()
    assert sent == []


@pytest.mark.asyncio
async def test_password_reset_enforces_durable_expiry_even_when_jwt_is_valid(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    from app.api.v1.endpoints import auth as auth_endpoint

    user = await _create_user(
        db_session,
        email="durable-reset-expiry@example.com",
        username="durable_reset_expiry",
    )
    sent: dict[str, str] = {}

    def capture_email(*, to: str, reset_url: str, language: str) -> bool:
        sent["token"] = reset_url.rsplit("token=", 1)[1]
        return True

    monkeypatch.setattr(auth_endpoint, "send_password_reset_email", capture_email)
    assert (
        await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user.email, "language": "en"},
        )
    ).status_code == 200
    grant = await db_session.get(
        PasswordResetToken,
        token_fingerprint(sent["token"]),
    )
    assert grant is not None
    grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    expired = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": sent["token"], "new_password": NEW_PASSWORD},
    )

    assert expired.status_code == 400
    await db_session.refresh(user)
    assert user.auth_version == 0


@pytest.mark.asyncio
async def test_cookie_password_change_requires_csrf_clears_cookies_and_rejects_old_access(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")
    user = await _create_user(
        db_session,
        email="cookie-password-change@example.com",
        username="cookie_password_change",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200
    old_access = client.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    old_refresh = client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    csrf = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert old_access and old_refresh and csrf

    missing_csrf = await client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert missing_csrf.status_code == 403
    changed = await client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf},
    )
    assert changed.status_code == 200, changed.text
    assert client.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME) is None
    assert client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) is None
    assert client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME) is None

    cookie_header = f"{settings.AUTH_ACCESS_COOKIE_NAME}={old_access}"
    old_cookie_access = await client.get(
        "/api/v1/auth/me",
        headers={"Cookie": cookie_header},
    )
    assert old_cookie_access.status_code == 401
    old_cookie_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh},
    )
    assert old_cookie_refresh.status_code == 401


@pytest.mark.asyncio
async def test_cookie_logout_revokes_access_cookie_and_refresh_family(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")
    user = await _create_user(
        db_session,
        email="cookie-logout@example.com",
        username="cookie_logout",
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200
    old_access = client.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    old_refresh = client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    csrf = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert old_access and old_refresh and csrf

    logout = await client.post(
        "/api/v1/auth/logout",
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf},
    )

    assert logout.status_code == 204
    assert await db_session.scalar(
        select(RevokedToken.id).where(
            RevokedToken.jti == token_fingerprint(old_access)
        )
    ) is not None
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_bearer_logout_without_refresh_body_durably_revokes_access(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(
        db_session,
        email="bearer-access-only-logout@example.com",
        username="bearer_access_only_logout",
    )
    access_token, _ = await _tokens(
        db_session,
        user,
        refresh_families=0,
    )

    logout = await client.post(
        "/api/v1/auth/logout",
        headers=_bearer(access_token),
    )

    assert logout.status_code == 204
    assert await db_session.scalar(
        select(RevokedToken.id).where(
            RevokedToken.jti == token_fingerprint(access_token)
        )
    ) is not None
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers=_bearer(access_token),
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_admin_deactivation_invalidates_tokens_after_reactivation(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    admin = await _create_user(
        db_session,
        email="deactivation-admin@example.com",
        username="deactivation_admin",
        role=UserRole.ADMIN,
    )
    target = await _create_user(
        db_session,
        email="deactivation-target@example.com",
        username="deactivation_target",
    )
    admin_access, _ = await _tokens(db_session, admin)
    old_access, old_refresh_tokens = await _tokens(db_session, target)

    deactivated = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        headers=_bearer(admin_access),
    )
    assert deactivated.status_code == 200, deactivated.text
    reactivated = await client.post(
        f"/api/v1/admin/users/{target.id}/activate",
        headers=_bearer(admin_access),
    )
    assert reactivated.status_code == 200, reactivated.text

    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": old_refresh_tokens[0]},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_password_change_invalidates_existing_plugin_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    user = await _create_user(
        db_session,
        email="plugin-password-change@example.com",
        username="plugin_password_change",
    )
    access_token, _ = await _tokens(db_session, user)
    plugin_session = await client.post(
        "/api/v1/auth/plugin-session",
        headers=_bearer(access_token),
    )
    assert plugin_session.status_code == 200, plugin_session.text
    plugin_token = plugin_session.json()["plugin_token"]
    assert (
        await client.get(
            "/api/v1/auth/my-presets",
            headers=_bearer(plugin_token),
        )
    ).status_code == 200

    changed = await client.patch(
        "/api/v1/auth/me/password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=_bearer(access_token),
    )
    assert changed.status_code == 200
    rejected = await client.get(
        "/api/v1/auth/my-presets",
        headers=_bearer(plugin_token),
    )
    assert rejected.status_code == 401
