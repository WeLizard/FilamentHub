"""Critical actions must require fresh, single-use proof and commit it atomically."""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import event, select

from app.api.v1.endpoints import auth as auth_endpoint
from app.core import security as security_module
from app.core.security import decode_access_token, generate_email_change_token
from app.db import session as session_module
from app.db.session import get_db
from app.main import app
from app.models.admin_action_confirmation import AdminActionConfirmation
from app.models.audit_event import AuditEvent
from app.models.user import User, UserRole
from app.services import admin_confirmation_service
from app.services.refresh_session_service import cleanup_expired_auth_state
from tests.admin_confirmation_helpers import issue_confirmation
from tests.auth_recovery_hardening_test import _bearer, _create_user, _tokens


async def actors(db):
    actor = await _create_user(
        db,
        email="confirmation-admin@example.com",
        username="proof_admin",
        role=UserRole.ADMIN,
        password=None,
        oauth=True,
    )
    target = await _create_user(
        db, email="confirmation-target@example.com", username="proof_target", password=None
    )
    access, refresh = await _tokens(db, actor, session_bound=True)
    return actor, target, _bearer(access), refresh[0]


@pytest.mark.parametrize(
    "action,path,method,reason",
    [
        ("block_user", "deactivate", "POST", "admin_block"),
        ("promote_admin", "promote-admin", "POST", "admin_promote"),
        ("demote_admin", "demote-to-user", "POST", "admin_demote"),
        ("delete_user", "", "DELETE", "admin_delete"),
    ],
)
async def test_action_requires_proof_and_audit_failure_leaves_it_retryable(
    client, db_session, monkeypatch, action, path, method, reason
):
    actor, target, headers, _ = await actors(db_session)
    if action == "demote_admin":
        target.role = UserRole.ADMIN
        await db_session.commit()
    actor_id, target_id, initial_role = actor.id, target.id, target.role
    url = f"/api/v1/admin/users/{target_id}" + (f"/{path}" if path else "")
    missing = await client.request(method, url, headers=headers, json={})
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "ERR_ADMIN_CONFIRMATION_REQUIRED"
    proof = await issue_confirmation(client, monkeypatch, headers, action, target_id)
    body = {"confirmation": proof, **({"delete_reviews": False} if action == "delete_user" else {})}

    def reject_audit(mapper, connection, target):
        raise RuntimeError("confirmation audit unavailable")

    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: db_session)
    app.dependency_overrides[get_db] = get_db
    event.listen(AuditEvent, "before_insert", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="confirmation audit unavailable"):
            await client.request(method, url, headers=headers, json=body)
    finally:
        event.remove(AuditEvent, "before_insert", reject_audit)
    persisted_target = await db_session.get(User, target_id)
    assert persisted_target.active and persisted_target.role == initial_role
    assert persisted_target.auth_version == 0
    challenge = await db_session.get(AdminActionConfirmation, proof["challenge_id"])
    assert challenge.consumed_at is None
    assert (await db_session.scalars(select(AuditEvent))).all() == []
    response = await client.request(method, url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    replay = await client.request(method, url, headers=headers, json=body)
    assert replay.status_code != 200
    await db_session.rollback()
    events = (await db_session.scalars(select(AuditEvent))).all()
    assert len(events) == 1 and events[0].reason == reason and events[0].actor_user_id == actor_id
    if action == "demote_admin":
        assert (await db_session.get(User, target_id)).auth_version == 1


@pytest.mark.parametrize(
    "mismatch", ["actor", "session", "action", "target", "parameters", "expiry"]
)
async def test_proof_cannot_authorize_a_different_operation_or_session(
    client, db_session, monkeypatch, mismatch
):
    actor, target, headers, _ = await actors(db_session)
    target_id = target.id
    proof = await issue_confirmation(
        client, monkeypatch, headers, "delete_user", target_id, delete_reviews=False
    )
    body = {"confirmation": proof, "delete_reviews": False}
    method, path = "DELETE", f"/api/v1/admin/users/{target_id}"
    if mismatch == "actor":
        target.role = UserRole.ADMIN
        await db_session.commit()
        access, _ = await _tokens(db_session, target, session_bound=True)
        headers = _bearer(access)
    elif mismatch == "session":
        access, _ = await _tokens(db_session, actor, session_bound=True)
        headers = _bearer(access)
    elif mismatch == "action":
        method, path = "POST", f"/api/v1/admin/users/{target_id}/promote-admin"
        body = {"confirmation": proof}
    elif mismatch == "target":
        path = f"/api/v1/admin/users/{actor.id}"
    elif mismatch == "parameters":
        body["delete_reviews"] = True
    else:
        challenge = await db_session.get(AdminActionConfirmation, proof["challenge_id"])
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db_session.commit()
    rejected = await client.request(method, path, headers=headers, json=body)
    assert rejected.status_code == 400, rejected.text
    await db_session.rollback()
    assert await db_session.get(User, target_id) is not None
    assert (await db_session.scalars(select(AuditEvent))).all() == []


async def test_attempt_budget_and_resend_are_durable_and_do_not_expose_the_code(
    client, db_session, monkeypatch, caplog
):
    _, target, headers, _ = await actors(db_session)
    proof = await issue_confirmation(client, monkeypatch, headers, "block_user", target.id)
    row = await db_session.get(AdminActionConfirmation, proof["challenge_id"])
    assert proof["code"] not in row.code_digest and len(row.code_digest) == 64
    wrong = "000000" if proof["code"] != "000000" else "999999"
    for index in range(5):
        rejected = await client.post(
            f"/api/v1/admin/users/{target.id}/deactivate",
            headers=headers,
            json={"confirmation": {**proof, "code": wrong}},
        )
        assert rejected.status_code == (400 if index < 4 else 429)
    assert row.attempts == 5
    exhausted = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate", headers=headers, json={"confirmation": proof}
    )
    assert exhausted.status_code == 429
    for _ in range(9):
        await issue_confirmation(client, monkeypatch, headers, "block_user", target.id)
    limited = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=headers,
        json={"action": "block_user", "target_user_id": target.id},
    )
    assert limited.status_code == 429
    assert row.delivered_at is None
    assert proof["code"] not in caplog.text


async def test_legacy_access_requires_refresh_and_refresh_preserves_the_family(
    client, db_session, monkeypatch
):
    actor, target, _, refresh = await actors(db_session)
    legacy_access, _ = await _tokens(db_session, actor, refresh_families=0)
    rejected = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=_bearer(legacy_access),
        json={"action": "block_user", "target_user_id": target.id},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "ERR_ADMIN_CONFIRMATION_SESSION_REQUIRED"
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    access = refreshed.json()["access_token"]
    sid = decode_access_token(access)["sid"]
    proof = await issue_confirmation(client, monkeypatch, _bearer(access), "block_user", target.id)
    refreshed_again = await client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": refreshed.json()["refresh_token"],
        },
    )
    fresh_access = refreshed_again.json()["access_token"]
    assert decode_access_token(fresh_access)["sid"] == sid
    result = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        headers=_bearer(fresh_access),
        json={"confirmation": proof},
    )
    assert result.status_code == 200


async def test_admin_email_change_binds_both_addresses_and_revokes_without_clearing_other_cookies(
    client, db_session, monkeypatch
):
    actor, _, headers, _ = await actors(db_session)
    actor_id = actor.id
    new_email = "admin-new-address@example.com"
    proof = await issue_confirmation(
        client, monkeypatch, headers, "change_admin_email", actor_id, new_email=new_email
    )
    sent = []
    monkeypatch.setattr(
        auth_endpoint, "send_email_change_email", lambda **mail: sent.append(mail) or True
    )
    wrong = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={
            "new_email": "different@example.com",
            "confirmation": proof,
        },
    )
    assert wrong.status_code == 400 and not sent
    requested = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert requested.status_code == 200
    assert actor.email == "confirmation-admin@example.com"
    token = parse_qs(urlparse(sent[0]["confirm_url"]).query)["token"][0]
    confirmed = await client.post("/api/v1/auth/confirm-email-change", params={"token": token})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["session_revoked"] is True
    assert confirmed.json()["user_id"] == actor_id
    assert "set-cookie" not in confirmed.headers
    assert actor.email == new_email and actor.auth_version == 1
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (
        await client.post("/api/v1/auth/confirm-email-change", params={"token": token})
    ).status_code == 400


async def test_rolled_back_email_link_cannot_be_revived_by_resend_or_demotion(
    client, db_session, monkeypatch, caplog
):
    actor, _, headers, _ = await actors(db_session)
    actor_id = actor.id
    new_email = "pending-admin-address@example.com"
    proof = await issue_confirmation(
        client, monkeypatch, headers, "change_admin_email", actor_id, new_email=new_email
    )
    sent = []
    monkeypatch.setattr(
        auth_endpoint, "send_email_change_email", lambda **mail: sent.append(mail) or False
    )
    failed = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={"new_email": new_email, "confirmation": proof},
    )
    assert failed.status_code == 503
    token = parse_qs(urlparse(sent[0]["confirm_url"]).query)["token"][0]
    await db_session.rollback()
    assert (
        await db_session.get(AdminActionConfirmation, proof["challenge_id"])
    ).consumed_at is None
    await issue_confirmation(
        client, monkeypatch, headers, "change_admin_email", actor_id, new_email=new_email
    )
    actor = await db_session.get(User, actor_id)
    actor.role = UserRole.USER
    await db_session.commit()
    replay = await client.post("/api/v1/auth/confirm-email-change", params={"token": token})
    assert replay.status_code == 400
    assert actor.email == "confirmation-admin@example.com"
    assert token not in caplog.text and proof["code"] not in caplog.text


async def test_legacy_email_change_is_rejected_for_admin_but_preserved_for_regular_user(
    client, db_session
):
    actor, target, _, _ = await actors(db_session)
    for user, expected in ((actor, 400), (target, 200)):
        token = generate_email_change_token(user.id, f"new-{user.id}@example.com")
        result = await client.post("/api/v1/auth/confirm-email-change", params={"token": token})
        assert result.status_code == expected
        if expected == 200:
            assert result.json()["session_revoked"] is False


async def test_delivery_failure_or_unverified_email_never_issues_a_usable_proof(
    client, db_session, monkeypatch
):
    actor, target, headers, _ = await actors(db_session)
    monkeypatch.setattr(
        admin_confirmation_service, "send_admin_confirmation_email", lambda **_: False
    )
    failed = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=headers,
        json={"action": "block_user", "target_user_id": target.id},
    )
    assert failed.status_code == 503
    row = (await db_session.scalars(select(AdminActionConfirmation))).one()
    assert row.delivered_at is None
    actor.email_verified = False
    await db_session.commit()
    rejected = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=headers,
        json={"action": "block_user", "target_user_id": target.id},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "ERR_ADMIN_CONFIRMATION_EMAIL_REQUIRED"


async def test_demotion_then_promotion_cannot_restore_a_previously_issued_proof(
    client, db_session, monkeypatch
):
    actor, target, headers, _ = await actors(db_session)
    other = await _create_user(
        db_session,
        email="other-admin@example.com",
        username="other_admin",
        role=UserRole.ADMIN,
        password=None,
    )
    other_access, _ = await _tokens(db_session, other, session_bound=True)
    other_headers = _bearer(other_access)
    proof = await issue_confirmation(client, monkeypatch, headers, "block_user", target.id)
    for action, path in (("demote_admin", "demote-to-user"), ("promote_admin", "promote-admin")):
        role_proof = await issue_confirmation(client, monkeypatch, other_headers, action, actor.id)
        changed = await client.post(
            f"/api/v1/admin/users/{actor.id}/{path}",
            headers=other_headers,
            json={"confirmation": role_proof},
        )
        assert changed.status_code == 200
    assert actor.role == UserRole.ADMIN and actor.auth_version == 1
    current_access, _ = await _tokens(db_session, actor, session_bound=True)
    replay = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        headers=_bearer(current_access),
        json={"confirmation": proof},
    )
    assert replay.status_code == 400 and target.active


async def test_confirmation_cleanup_is_bounded_and_retains_pending_email_links(
    client, db_session, monkeypatch
):
    actor, target, headers, _ = await actors(db_session)
    proofs = [
        await issue_confirmation(client, monkeypatch, headers, "block_user", target.id)
        for _ in range(3)
    ]
    now = datetime.now(timezone.utc)
    for proof in proofs[:2]:
        row = await db_session.get(AdminActionConfirmation, proof["challenge_id"])
        row.created_at = now - timedelta(days=3)
    recent = await db_session.get(AdminActionConfirmation, proofs[2]["challenge_id"])
    recent.created_at = now - timedelta(hours=20)
    recent.expires_at = now - timedelta(hours=19)
    recent.consumed_at = now - timedelta(hours=19)
    recent.action = "change_admin_email"
    await db_session.commit()
    result = await cleanup_expired_auth_state(db_session, now=now, batch_size=1)
    await db_session.commit()
    assert result.admin_confirmations == 1
    remaining = (await db_session.scalars(select(AdminActionConfirmation))).all()
    assert len(remaining) == 2
    assert any(row.id == proofs[2]["challenge_id"] for row in remaining)


async def test_access_only_logout_invalidates_codes_and_pending_email_links_after_refresh(
    client, db_session, monkeypatch
):
    actor, target, headers, refresh = await actors(db_session)
    proof = await issue_confirmation(client, monkeypatch, headers, "block_user", target.id)
    email_proof = await issue_confirmation(
        client,
        monkeypatch,
        headers,
        "change_admin_email",
        actor.id,
        new_email="pending-logout-email@example.com",
    )
    sent = []
    monkeypatch.setattr(
        auth_endpoint, "send_email_change_email", lambda **mail: sent.append(mail) or True
    )
    email_requested = await client.patch(
        "/api/v1/auth/me/email",
        headers=headers,
        json={
            "new_email": "pending-logout-email@example.com",
            "confirmation": email_proof,
        },
    )
    assert email_requested.status_code == 200
    email_token = parse_qs(urlparse(sent[0]["confirm_url"]).query)["token"][0]
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    for issued in (proof, email_proof):
        assert (
            await db_session.get(AdminActionConfirmation, issued["challenge_id"])
        ).delivered_at is None

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=2)

    # Advance token issuance past the old token's second without a wall-clock sleep.
    monkeypatch.setattr(security_module, "datetime", Later)
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    current_headers = _bearer(refreshed.json()["access_token"])
    rejected_code = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        headers=current_headers,
        json={"confirmation": proof},
    )
    assert rejected_code.status_code == 400
    rejected_link = await client.post(
        "/api/v1/auth/confirm-email-change", params={"token": email_token}
    )
    assert rejected_link.status_code == 400
    fresh_proof = await issue_confirmation(
        client, monkeypatch, current_headers, "block_user", target.id
    )
    accepted = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        headers=current_headers,
        json={"confirmation": fresh_proof},
    )
    assert accepted.status_code == 200


async def test_logout_during_smtp_cannot_reactivate_the_cancelled_confirmation(
    client, db_session, monkeypatch
):
    _, target, headers, _ = await actors(db_session)

    async def delivery_after_logout(function, **mail):
        assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
        return True

    monkeypatch.setattr(admin_confirmation_service.asyncio, "to_thread", delivery_after_logout)
    issued = await client.post(
        "/api/v1/admin/reauth/challenges",
        headers=headers,
        json={"action": "block_user", "target_user_id": target.id},
    )
    assert issued.status_code == 400
    challenge = (await db_session.scalars(select(AdminActionConfirmation))).one()
    assert challenge.delivered_at is None and challenge.consumed_at is not None
