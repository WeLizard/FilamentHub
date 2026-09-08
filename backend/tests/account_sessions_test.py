"""Session control must revoke the selected login, preserving independent credentials."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import event, select
from starlette.requests import Request

from app.core.config import settings
from app.core.dependencies import get_current_active_user_optional, require_preset_read
from app.core.security import (
    create_access_token,
    create_plugin_token,
    create_refresh_token,
    create_session_access_token,
    decode_access_token,
    decode_refresh_token,
)
from app.db import session as session_module
from app.db.session import get_db
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.refresh_session import RefreshSession
from app.services.account_auth_service import token_data_for_user
from app.services.account_session_service import persist_session_activity, validate_access_family
from app.services.refresh_session_service import issue_refresh_session
from tests.auth_recovery_hardening_test import _bearer, _create_user, _tokens


def request_for(access: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"authorization", f"Bearer {access}".encode()),
            ],
        }
    )


async def setup_sessions(db):
    user = await _create_user(db, email="sessions@example.com", username="sessions", password=None)
    first, first_refreshes = await _tokens(db, user, session_bound=True)
    second, second_refreshes = await _tokens(db, user, session_bound=True)
    return user, first, first_refreshes[0], second, second_refreshes[0]


async def test_session_list_is_owned_paginated_and_has_only_safe_metadata(client, db_session):
    user, first, _, second, _ = await setup_sessions(db_session)
    claims = token_data_for_user(user)
    refresh = await issue_refresh_session(
        db_session,
        user_id=user.id,
        token_data=claims,
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36 private-host private-ip",
    )
    await db_session.commit()
    current = create_session_access_token(claims, refresh)
    other = await _create_user(
        db_session, email="other-sessions@example.com", username="other_sessions", password=None
    )
    await _tokens(db_session, other, session_bound=True)
    revoked = await db_session.get(RefreshSession, decode_access_token(first)["sid"])
    revoked.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()
    response = await client.get("/api/v1/auth/sessions?size=1", headers=_bearer(current))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2 and body["pages"] == 2
    assert body["current_session_id"] == decode_refresh_token(refresh)["sid"]
    item = body["items"][0]
    assert item["is_current"] and item["id"] == body["current_session_id"]
    assert (item["browser"], item["os"], item["device_type"]) == ("chrome", "windows", "desktop")
    assert set(item) == {
        "id",
        "is_current",
        "created_at",
        "last_seen_at",
        "expires_at",
        "browser",
        "os",
        "device_type",
    }
    assert "private-host" not in response.text and "private-ip" not in response.text
    assert response.headers["cache-control"] == "private, no-store"
    next_page = await client.get("/api/v1/auth/sessions?page=2&size=1", headers=_bearer(current))
    assert next_page.json()["items"][0]["id"] == decode_access_token(second)["sid"]
    assert not next_page.json()["items"][0]["is_current"]


async def test_selected_revocation_stops_all_access_and_refresh_but_preserves_other_credentials(
    client, db_session
):
    user, first, first_refresh, second, second_refresh = await setup_sessions(db_session)
    sid = decode_access_token(second)["sid"]
    # The same family may hold several access tokens after refresh.
    additional = create_session_access_token(token_data_for_user(user), second_refresh)
    plugin = create_plugin_token(token_data_for_user(user), ["presets:read"])
    user.api_key = "independent-device-credential"
    await db_session.commit()
    foreign = await _create_user(
        db_session, email="foreign-session@example.com", username="foreign_session", password=None
    )
    foreign_access, _ = await _tokens(db_session, foreign, session_bound=True)
    denied = await client.delete(f"/api/v1/auth/sessions/{sid}", headers=_bearer(foreign_access))
    assert denied.status_code == 404
    revoked = await client.delete(f"/api/v1/auth/sessions/{sid}", headers=_bearer(first))
    assert revoked.json() == {"revoked": True, "current_session_revoked": False}
    assert "set-cookie" not in revoked.headers
    for token in (second, additional):
        assert (await client.get("/api/v1/auth/me", headers=_bearer(token))).status_code == 401
        assert await get_current_active_user_optional(request_for(token), db_session) is None
        with pytest.raises(HTTPException) as rejection:
            await require_preset_read(
                request_for(token),
                HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                db_session,
            )
        assert rejection.value.status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh})
    ).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=_bearer(first))).status_code == 200
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    ).status_code == 200
    assert (
        await require_preset_read(
            request_for(plugin),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=plugin),
            db_session,
        )
    ).id == user.id
    assert user.auth_version == 0 and user.api_key == "independent-device-credential"
    retry = await client.delete(f"/api/v1/auth/sessions/{sid}", headers=_bearer(first))
    assert retry.json() == {"revoked": False, "current_session_revoked": False}
    assert len((await db_session.scalars(select(AuditEvent))).all()) == 1


async def test_revoke_others_preserves_current_family_and_closes_unregistered_legacy(
    client, db_session
):
    user, first, first_refresh, second, second_refresh = await setup_sessions(db_session)
    claims = token_data_for_user(user)
    legacy_refresh = create_refresh_token(claims)
    legacy_access = create_access_token(claims)
    required = await client.get("/api/v1/auth/sessions", headers=_bearer(legacy_access))
    assert (
        required.status_code == 401 and required.json()["detail"]["code"] == "ERR_SESSION_REQUIRED"
    )
    assert required.headers["www-authenticate"] == "Bearer"
    revoked = await client.post(
        "/api/v1/auth/sessions/revoke-others",
        headers=_bearer(first),
        json={"current_session_id": decode_access_token(second)["sid"]},
    )
    assert revoked.status_code == 200 and revoked.json()["revoked_count"] == 1
    assert (await client.get("/api/v1/auth/me", headers=_bearer(legacy_access))).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": legacy_refresh})
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": second_refresh})
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    ).status_code == 200
    retry = await client.post("/api/v1/auth/sessions/revoke-others", headers=_bearer(first))
    assert retry.json() == {"revoked_count": 0}
    assert len((await db_session.scalars(select(AuditEvent))).all()) == 1


@pytest.mark.parametrize("operation", ["selected", "others"])
async def test_session_revoke_audit_failure_rolls_back_family_and_legacy_markers(
    client, db_session, monkeypatch, operation
):
    user, first, _, second, _ = await setup_sessions(db_session)
    user_id, sid = user.id, decode_access_token(second)["sid"]
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: db_session)
    app.dependency_overrides[get_db] = get_db

    def fail(*_):
        raise RuntimeError("session audit failed")

    event.listen(AuditEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="session audit failed"):
            if operation == "selected":
                await client.delete(f"/api/v1/auth/sessions/{sid}", headers=_bearer(first))
            else:
                await client.post("/api/v1/auth/sessions/revoke-others", headers=_bearer(first))
    finally:
        event.remove(AuditEvent, "before_insert", fail)
    from app.models.user import User

    user = await db_session.get(User, user_id)
    assert user.legacy_access_revoked_at is None and user.legacy_refresh_disabled_at is None
    assert (await db_session.get(RefreshSession, sid)).revoked_at is None
    assert (await client.get("/api/v1/auth/me", headers=_bearer(second))).status_code == 200


async def test_session_control_cookie_csrf_and_self_revoke_do_not_clear_replacement_cookies(
    client, db_session, monkeypatch
):
    _, first, _, _, _ = await setup_sessions(db_session)
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")
    sid = decode_access_token(first)["sid"]
    client.cookies.set(settings.AUTH_ACCESS_COOKIE_NAME, first)
    client.cookies.set(settings.AUTH_CSRF_COOKIE_NAME, "csrf")
    assert (await client.delete(f"/api/v1/auth/sessions/{sid}")).status_code == 403
    response = await client.delete(
        f"/api/v1/auth/sessions/{sid}", headers={settings.AUTH_CSRF_HEADER_NAME: "csrf"}
    )
    assert response.status_code == 200 and response.json()["current_session_revoked"] is True
    assert "set-cookie" not in response.headers
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_activity_is_sampled_after_business_transaction_and_does_not_revive_a_family(
    db_session,
):
    user, first, _, _, _ = await setup_sessions(db_session)
    payload = decode_access_token(first)
    row = await db_session.get(RefreshSession, payload["sid"])
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    row.last_seen_at = old
    await db_session.commit()
    assert await validate_access_family(
        db_session, payload=payload, user=user, request=request_for(first)
    )
    assert row.last_seen_at == old  # Authentication itself holds no family write lock.
    await db_session.commit()
    await persist_session_activity(db_session)
    await db_session.refresh(row)
    recorded = row.last_seen_at
    assert recorded.replace(tzinfo=timezone.utc) > old
    assert await validate_access_family(
        db_session, payload=payload, user=user, request=request_for(first)
    )
    assert not db_session.info.get("account_session_activity")
    row.last_seen_at = old
    await db_session.commit()
    assert await validate_access_family(
        db_session, payload=payload, user=user, request=request_for(first)
    )
    row.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()
    await persist_session_activity(db_session)
    await db_session.refresh(row)
    assert row.last_seen_at.replace(tzinfo=timezone.utc) == old


async def test_legacy_list_refresh_upgrade_and_selected_revoke_cannot_replay_old_access(
    client, db_session
):
    user, controller, _, _, _ = await setup_sessions(db_session)
    claims = token_data_for_user(user)
    old_access = create_access_token(claims)
    legacy_refresh = create_refresh_token(claims)
    assert (
        await client.get("/api/v1/auth/sessions", headers=_bearer(old_access))
    ).status_code == 401
    upgraded = await client.post("/api/v1/auth/refresh", json={"refresh_token": legacy_refresh})
    assert upgraded.status_code == 200
    access = upgraded.json()["access_token"]
    sid = decode_access_token(access)["sid"]
    listed = await client.get("/api/v1/auth/sessions", headers=_bearer(access))
    assert listed.status_code == 200 and listed.json()["current_session_id"] == sid
    assert (
        await client.delete(f"/api/v1/auth/sessions/{sid}", headers=_bearer(controller))
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=_bearer(old_access))).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=_bearer(access))).status_code == 401
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": legacy_refresh})
    ).status_code == 401


async def test_bound_refresh_updates_approximate_activity_without_sliding_expiry(
    client, db_session
):
    _, first, refresh, _, _ = await setup_sessions(db_session)
    row = await db_session.get(RefreshSession, decode_access_token(first)["sid"])
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    row.last_seen_at = old
    expiry = row.expires_at
    await db_session.commit()
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert response.status_code == 200
    await db_session.refresh(row)
    assert row.last_seen_at.replace(tzinfo=timezone.utc) > old
    assert row.expires_at.replace(tzinfo=timezone.utc) == expiry.replace(tzinfo=timezone.utc)
