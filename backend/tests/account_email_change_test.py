"""Regular account email changes require both-address proof and revoke auth state."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.api.v1.endpoints import auth as auth_endpoint
from app.core.security import create_access_token, create_session_access_token
from app.models.account_email_change_confirmation import AccountEmailChangeConfirmation
from app.models.refresh_session import RefreshSession
from app.models.user import User
from app.services import account_email_change_service
from app.services.account_auth_service import token_data_for_user
from tests.auth_recovery_hardening_test import _bearer, _create_user, _tokens


async def issue_challenge(client, monkeypatch, headers, new_email: str):
    delivered: list[dict] = []

    def capture_code(**mail):
        delivered.append(mail)
        return True

    monkeypatch.setattr(
        account_email_change_service,
        "send_account_email_change_code",
        capture_code,
    )
    response = await client.post(
        "/api/v1/auth/me/email-change/challenges",
        headers=headers,
        json={"new_email": new_email, "language": "en"},
    )
    assert response.status_code == 200, response.text
    return {
        "challenge_id": response.json()["challenge_id"],
        "code": delivered[-1]["code"],
    }


async def test_oauth_only_email_change_binds_new_address_and_revokes_every_session(
    client, db_session, monkeypatch
):
    user = await _create_user(
        db_session,
        email="oauth-email-change@example.com",
        username="oauth_email_change",
        password=None,
        oauth=True,
    )
    user_id = user.id
    old_email = user.email
    access, refresh_tokens = await _tokens(
        db_session, user, refresh_families=2, session_bound=True
    )
    headers = _bearer(access)
    new_email = "oauth-email-changed@example.com"
    proof = await issue_challenge(client, monkeypatch, headers, new_email)

    wrong_address = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={
            "new_email": "other-address@example.com",
            "confirmation": proof,
        },
    )
    assert wrong_address.status_code == 400
    assert wrong_address.json()["detail"]["code"] == "ERR_EMAIL_CHANGE_INVALID"

    wrong_code = "000000" if proof["code"] != "000000" else "999999"
    rejected = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={
            "new_email": new_email,
            "confirmation": {**proof, "code": wrong_code},
        },
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "ERR_EMAIL_CHANGE_INVALID"

    links: list[str] = []
    notices: list[dict] = []
    monkeypatch.setattr(
        auth_endpoint,
        "send_email_change_email",
        lambda **mail: links.append(mail["confirm_url"]) or True,
    )
    monkeypatch.setattr(
        auth_endpoint,
        "send_email_change_completed",
        lambda **mail: notices.append(mail) or True,
    )
    requested = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert requested.status_code == 200, requested.text
    replayed_proof = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert replayed_proof.status_code == 400

    token = parse_qs(urlparse(links[0]).query)["token"][0]
    confirmed = await client.post(
        "/api/v1/auth/confirm-email-change", params={"token": token}
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {
        "message": "Email успешно изменён",
        "session_revoked": True,
        "user_id": user_id,
    }
    await db_session.refresh(user)
    assert user.email == new_email
    assert user.email_verified is True
    assert user.auth_version == 1
    assert notices == [{"to": old_email, "new_email": new_email, "language": None}]

    sessions = (
        await db_session.scalars(
            select(RefreshSession).where(RefreshSession.user_id == user_id)
        )
    ).all()
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    for refresh_token in refresh_tokens:
        refreshed = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert refreshed.status_code == 401
    replayed_link = await client.post(
        "/api/v1/auth/confirm-email-change", params={"token": token}
    )
    assert replayed_link.status_code == 400


async def test_email_change_proof_rejects_session_mismatch_expiry_and_unverified_current_email(
    client, db_session, monkeypatch
):
    user = await _create_user(
        db_session,
        email="email-proof-binding@example.com",
        username="email_proof_binding",
    )
    legacy_access = create_access_token(token_data_for_user(user))
    session_required = await client.post(
        "/api/v1/auth/me/email-change/challenges",
        headers=_bearer(legacy_access),
        json={"new_email": "legacy-session@example.com"},
    )
    assert session_required.status_code == 403
    assert (
        session_required.json()["detail"]["code"]
        == "ERR_EMAIL_CHANGE_SESSION_REQUIRED"
    )
    first_access, refresh_tokens = await _tokens(
        db_session, user, refresh_families=2, session_bound=True
    )
    first_headers = _bearer(first_access)
    new_email = "email-proof-bound@example.com"
    proof = await issue_challenge(client, monkeypatch, first_headers, new_email)
    second_access = create_session_access_token(
        token_data_for_user(user), refresh_tokens[1]
    )

    wrong_session = await client.patch(
        "/api/v1/auth/me/email",
        headers=_bearer(second_access),
        json={"new_email": new_email, "confirmation": proof},
    )
    assert wrong_session.status_code == 400
    assert wrong_session.json()["detail"]["code"] == "ERR_EMAIL_CHANGE_INVALID"

    challenge = await db_session.get(
        AccountEmailChangeConfirmation, proof["challenge_id"]
    )
    challenge.auth_version += 1
    await db_session.commit()
    wrong_auth_version = await client.patch(
        "/api/v1/auth/me/email",
        headers=first_headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert wrong_auth_version.status_code == 400
    assert wrong_auth_version.json()["detail"]["code"] == "ERR_EMAIL_CHANGE_INVALID"

    challenge.auth_version = user.auth_version
    challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    expired = await client.patch(
        "/api/v1/auth/me/email",
        headers=first_headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert expired.status_code == 400
    assert expired.json()["detail"]["code"] == "ERR_EMAIL_CHANGE_EXPIRED"

    user.email_verified = False
    await db_session.commit()
    unverified = await client.post(
        "/api/v1/auth/me/email-change/challenges",
        headers=first_headers,
        json={"new_email": "unverified-new@example.com"},
    )
    assert unverified.status_code == 403
    assert (
        unverified.json()["detail"]["code"]
        == "ERR_EMAIL_CHANGE_CURRENT_EMAIL_REQUIRED"
    )


async def test_delivery_failures_never_create_a_usable_email_change_link(
    client, db_session, monkeypatch
):
    user = await _create_user(
        db_session,
        email="email-delivery-failure@example.com",
        username="email_delivery_failure",
    )
    access, _ = await _tokens(db_session, user, session_bound=True)
    headers = _bearer(access)
    new_email = "email-delivery-replacement@example.com"
    failed_codes: list[str] = []

    def fail_code(**mail):
        failed_codes.append(mail["code"])
        return False

    monkeypatch.setattr(
        account_email_change_service,
        "send_account_email_change_code",
        fail_code,
    )
    failed_challenge = await client.post(
        "/api/v1/auth/me/email-change/challenges",
        headers=headers,
        json={"new_email": new_email},
    )
    assert failed_challenge.status_code == 503
    failed_row = (
        await db_session.scalars(select(AccountEmailChangeConfirmation))
    ).one()
    assert failed_row.delivered_at is None
    rejected = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={
            "new_email": new_email,
            "confirmation": {
                "challenge_id": failed_row.id,
                "code": failed_codes[0],
            },
        },
    )
    assert rejected.status_code == 400

    proof = await issue_challenge(client, monkeypatch, headers, new_email)
    failed_links: list[str] = []
    monkeypatch.setattr(
        auth_endpoint,
        "send_email_change_email",
        lambda **mail: failed_links.append(mail["confirm_url"]) or False,
    )
    failed_link = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert failed_link.status_code == 503
    token = parse_qs(urlparse(failed_links[0]).query)["token"][0]
    unusable = await client.post(
        "/api/v1/auth/confirm-email-change", params={"token": token}
    )
    assert unusable.status_code == 400
    persisted = await db_session.get(User, user.id)
    assert persisted.email == "email-delivery-failure@example.com"
