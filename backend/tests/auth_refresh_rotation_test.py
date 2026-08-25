"""Refresh-token rotation, replay containment, and retention regressions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.v1.endpoints.auth import _set_auth_cookies
from app.core.config import settings
from app.core.security import create_refresh_token, decode_refresh_token
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_PRIVACY_POLICY_VERSION,
    CURRENT_TERMS_VERSION,
)
from app.services.refresh_session_service import (
    REFRESH_RETRY_GRACE_SECONDS,
    cleanup_expired_auth_state,
)


def _registration(email: str, username: str) -> dict[str, object]:
    return {
        "email": email,
        "username": username,
        "password": "password123",
        "role": "user",
        "terms_accepted": True,
        "personal_data_consent": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "personal_data_consent_version": CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        "privacy_policy_version": CURRENT_PRIVACY_POLICY_VERSION,
        "legal_language": "ru",
    }


async def _register_and_login(
    client: AsyncClient,
    *,
    email: str,
    username: str,
) -> dict:
    created = await client.post("/api/v1/auth/register", json=_registration(email, username))
    assert created.status_code == 201, created.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return login.json()


@pytest.mark.asyncio
async def test_each_login_issues_a_distinct_refresh_family(client: AsyncClient) -> None:
    first = await _register_and_login(
        client,
        email="refresh-families@example.com",
        username="refresh_families",
    )
    second = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh-families@example.com", "password": "password123"},
    )
    assert second.status_code == 200

    first_payload = decode_refresh_token(first["refresh_token"])
    second_payload = decode_refresh_token(second.json()["refresh_token"])
    assert first_payload is not None
    assert second_payload is not None
    assert first["refresh_token"] != second.json()["refresh_token"]
    assert first_payload["sid"] != second_payload["sid"]
    assert first_payload["jti"] != second_payload["jti"]


@pytest.mark.asyncio
async def test_body_refresh_rotates_with_fixed_expiry_and_idempotent_retry(
    client: AsyncClient,
) -> None:
    login = await _register_and_login(
        client,
        email="refresh-rotation@example.com",
        username="refresh_rotation",
    )
    first = login["refresh_token"]
    first_payload = decode_refresh_token(first)
    assert first_payload is not None

    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()["refresh_token"]
    second_payload = decode_refresh_token(second)
    assert second != first
    assert second_payload is not None
    assert second_payload["sid"] == first_payload["sid"]
    assert second_payload["exp"] == first_payload["exp"]

    retry = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["refresh_token"] == second


@pytest.mark.asyncio
async def test_overlapping_generations_do_not_revoke_a_legitimate_retry(
    client: AsyncClient,
) -> None:
    login = await _register_and_login(
        client,
        email="refresh-overlap@example.com",
        username="refresh_overlap",
    )
    first = login["refresh_token"]

    first_rotation = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    assert first_rotation.status_code == 200, first_rotation.text
    second = first_rotation.json()["refresh_token"]

    # A second tab may already have received the successor while another
    # response using the predecessor is still in flight.  During the bounded
    # retry window the successor stays stable instead of advancing a generation.
    overlapping = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second},
    )
    assert overlapping.status_code == 200, overlapping.text
    assert overlapping.json()["refresh_token"] == second

    delayed_predecessor = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    assert delayed_predecessor.status_code == 200, delayed_predecessor.text
    assert delayed_predecessor.json()["refresh_token"] == second

    family_still_valid = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second},
    )
    assert family_still_valid.status_code == 200, family_still_valid.text


@pytest.mark.asyncio
async def test_reuse_after_grace_revokes_only_that_refresh_family(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    login = await _register_and_login(
        client,
        email="refresh-reuse@example.com",
        username="refresh_reuse",
    )
    first = login["refresh_token"]
    other_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh-reuse@example.com", "password": "password123"},
    )
    assert other_login.status_code == 200
    other_family = other_login.json()["refresh_token"]

    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    second = rotated.json()["refresh_token"]
    payload = decode_refresh_token(first)
    assert payload is not None
    session = await db_session.get(RefreshSession, payload["sid"])
    assert session is not None
    session.rotated_at = datetime.now(timezone.utc) - timedelta(
        seconds=REFRESH_RETRY_GRACE_SECONDS + 1
    )
    await db_session.commit()

    replay = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    assert replay.status_code == 401

    descendant = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second},
    )
    assert descendant.status_code == 401

    independent = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": other_family},
    )
    assert independent.status_code == 200


@pytest.mark.asyncio
async def test_legacy_refresh_token_upgrades_without_forced_logout(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    login = await _register_and_login(
        client,
        email="refresh-legacy@example.com",
        username="refresh_legacy",
    )
    login_payload = decode_refresh_token(login["refresh_token"])
    assert login_payload is not None
    legacy = create_refresh_token(
        {
            "sub": login_payload["sub"],
            "user_id": login_payload["user_id"],
            "role": login_payload["role"],
        }
    )
    assert "sid" not in (decode_refresh_token(legacy) or {})

    upgraded = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": legacy},
    )
    assert upgraded.status_code == 200, upgraded.text
    replacement = upgraded.json()["refresh_token"]
    replacement_payload = decode_refresh_token(replacement)
    assert replacement_payload is not None
    assert replacement_payload.get("sid")
    assert await db_session.get(RefreshSession, replacement_payload["sid"]) is not None

    retry = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": legacy},
    )
    assert retry.status_code == 200
    assert retry.json()["refresh_token"] == replacement


@pytest.mark.asyncio
async def test_cookie_refresh_rotates_http_only_cookie_without_exposing_successor(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")
    await _register_and_login(
        client,
        email="refresh-cookie@example.com",
        username="refresh_cookie",
    )
    old_refresh = client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    csrf = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert old_refresh and csrf

    response = await client.post(
        "/api/v1/auth/refresh",
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["refresh_token"] is None
    assert client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME) != old_refresh


def test_refresh_cookie_uses_the_tokens_remaining_fixed_lifetime() -> None:
    refresh_token = create_refresh_token(
        {"sub": "cookie-expiry@example.com", "user_id": 1, "role": "user"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        session_id="cookie-expiry-session",
    )
    response = Response()

    _set_auth_cookies(response, "access-token", refresh_token)

    refresh_cookie = next(
        value
        for value in response.headers.getlist("set-cookie")
        if value.startswith(f"{settings.AUTH_REFRESH_COOKIE_NAME}=")
    )
    max_age = int(refresh_cookie.split("Max-Age=", 1)[1].split(";", 1)[0])
    assert 295 <= max_age <= 300


def test_refresh_cookie_expiring_during_rotation_is_cleared_not_raised() -> None:
    refresh_token = create_refresh_token(
        {"sub": "expired-cookie@example.com", "user_id": 1, "role": "user"},
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        session_id="expired-cookie-session",
    )
    response = Response()

    _set_auth_cookies(response, "access-token", refresh_token)

    refresh_cookie = next(
        value
        for value in response.headers.getlist("set-cookie")
        if value.startswith(f"{settings.AUTH_REFRESH_COOKIE_NAME}=")
    )
    assert "Max-Age=0" in refresh_cookie


@pytest.mark.asyncio
async def test_logout_with_rotated_predecessor_revokes_the_family(
    client: AsyncClient,
) -> None:
    login = await _register_and_login(
        client,
        email="refresh-logout@example.com",
        username="refresh_logout",
    )
    first = login["refresh_token"]
    rotated = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": first},
    )
    second = rotated.json()["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": first},
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )
    assert logout.status_code == 204, logout.text
    rejected = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": second},
    )
    assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_invalid_refresh_input_creates_no_auth_state(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    before_sessions = await db_session.scalar(select(func.count(RefreshSession.id)))
    before_revocations = await db_session.scalar(select(func.count(RevokedToken.id)))
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-jwt"},
    )
    assert response.status_code == 401
    assert await db_session.scalar(select(func.count(RefreshSession.id))) == before_sessions
    assert await db_session.scalar(select(func.count(RevokedToken.id))) == before_revocations


@pytest.mark.asyncio
async def test_cleanup_is_bounded_and_keeps_clock_skew_window(
    db_session: AsyncSession,
) -> None:
    now = datetime.now(timezone.utc)
    for number, expires_at in enumerate(
        (
            now - timedelta(minutes=5),
            now - timedelta(minutes=4),
            now - timedelta(seconds=30),
            now + timedelta(minutes=1),
        )
    ):
        db_session.add(
            RevokedToken(jti=f"{number:064x}", expires_at=expires_at)
        )
        db_session.add(
            RefreshSession(
                id=f"session-{number}",
                user_id=1,
                current_token_fingerprint=f"{number + 100:064x}",
                expires_at=expires_at,
                rotated_at=now,
                created_at=now,
            )
        )
    await db_session.commit()

    removed = await cleanup_expired_auth_state(db_session, now=now, batch_size=1)
    await db_session.commit()
    assert removed.revoked_tokens == 1
    assert removed.refresh_sessions == 1
    assert await db_session.scalar(select(func.count(RevokedToken.id))) == 3
    assert await db_session.scalar(select(func.count(RefreshSession.id))) == 3

    removed_again = await cleanup_expired_auth_state(db_session, now=now, batch_size=10)
    await db_session.commit()
    assert removed_again.revoked_tokens == 1
    assert removed_again.refresh_sessions == 1
    assert await db_session.scalar(select(func.count(RevokedToken.id))) == 2
    assert await db_session.scalar(select(func.count(RefreshSession.id))) == 2
