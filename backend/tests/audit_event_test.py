"""Durable security audit must fail atomically and never retain credentials."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import delete, event, select, text

from app.core.security import decode_refresh_token
from app.db import session as session_module
from app.db.session import get_db
from app.main import app
from app.models.audit_event import AuditAction, AuditEvent, AuditReason
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_session import RefreshSession
from app.models.revoked_token import RevokedToken
from app.models.user import User, UserRole
from app.services.account_auth_service import issue_password_reset_grant, reset_password_with_grant
from app.services.audit_service import record_audit_event
from app.services.refresh_session_service import REFRESH_RETRY_GRACE_SECONDS, rotate_refresh_session
from tests.auth_recovery_hardening_test import (
    NEW_PASSWORD,
    OLD_PASSWORD,
    _bearer,
    _create_user,
    _tokens,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation", ["password_change", "password_reset", "admin_block", "logout", "refresh_reuse"]
)
async def test_audit_insert_failure_rolls_back_the_actual_http_mutation(
    client, db_session, monkeypatch, operation
):
    user = await _create_user(
        db_session, email="audit-failure@example.com", username="audit_failure"
    )
    admin = await _create_user(
        db_session, email="audit-admin@example.com", username="audit_admin", role=UserRole.ADMIN
    )
    access, refresh_tokens = await _tokens(db_session, user)
    admin_access, _ = await _tokens(db_session, admin, session_bound=True)
    from tests.admin_confirmation_helpers import issue_confirmation

    proof = (
        await issue_confirmation(client, monkeypatch, _bearer(admin_access), "block_user", user.id)
        if operation == "admin_block"
        else None
    )
    grant = await issue_password_reset_grant(db_session, user=user)
    await db_session.commit()
    user_id, original_hash = user.id, user.password_hash
    refresh = refresh_tokens[0]
    payload = decode_refresh_token(refresh)
    if operation == "refresh_reuse":
        await rotate_refresh_session(
            db_session, refresh_token=refresh, payload=payload, user_id=user_id
        )
        family = await db_session.get(RefreshSession, payload["sid"])
        family.rotated_at = datetime.now(timezone.utc) - timedelta(
            seconds=REFRESH_RETRY_GRACE_SECONDS + 1
        )
        await db_session.commit()

    # Exercise production get_db's rollback, not the ordinary test dependency,
    # which intentionally keeps a shared session open without transaction handling.
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: db_session)
    app.dependency_overrides[get_db] = get_db

    def reject_audit_insert(mapper, connection, target):
        raise RuntimeError("audit storage unavailable")

    event.listen(AuditEvent, "before_insert", reject_audit_insert)
    try:
        with pytest.raises(RuntimeError, match="audit storage unavailable"):
            if operation == "password_change":
                await client.patch(
                    "/api/v1/auth/me/password",
                    headers=_bearer(access),
                    json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
                )
            elif operation == "password_reset":
                await client.post(
                    "/api/v1/auth/reset-password",
                    json={"token": grant, "new_password": NEW_PASSWORD},
                )
            elif operation == "admin_block":
                await client.post(
                    f"/api/v1/admin/users/{user_id}/deactivate",
                    headers=_bearer(admin_access),
                    json={"confirmation": proof},
                )
            elif operation == "logout":
                await client.post(
                    "/api/v1/auth/logout", headers=_bearer(access), json={"refresh_token": refresh}
                )
            else:
                await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    finally:
        event.remove(AuditEvent, "before_insert", reject_audit_insert)

    persisted = await db_session.get(User, user_id)
    assert persisted.active
    assert persisted.password_hash == original_hash
    assert persisted.auth_version == 0
    assert (await db_session.scalars(select(AuditEvent))).all() == []
    assert (await db_session.scalars(select(RevokedToken))).all() == []
    assert all(
        family.revoked_at is None
        for family in (await db_session.scalars(select(RefreshSession))).all()
    )
    assert all(
        token.consumed_at is None
        for token in (await db_session.scalars(select(PasswordResetToken))).all()
    )


@pytest.mark.asyncio
async def test_reset_audit_obeys_explicit_rollback_and_contains_only_bounded_facts(db_session):
    user = await _create_user(
        db_session, email="private-audit@example.com", username="private_audit"
    )
    token = await issue_password_reset_grant(db_session, user=user)
    await db_session.commit()
    user_id, old_hash = user.id, user.password_hash
    await reset_password_with_grant(
        db_session, token=token, password_hash="private-new-password-hash"
    )
    assert (await db_session.scalars(select(AuditEvent))).one().target_user_id == user_id
    await db_session.rollback()
    assert (await db_session.scalars(select(AuditEvent))).all() == []
    assert (await db_session.get(User, user_id)).password_hash == old_hash

    await reset_password_with_grant(
        db_session, token=token, password_hash="private-new-password-hash"
    )
    await db_session.commit()
    row = (await db_session.scalars(select(AuditEvent))).one()
    assert isinstance(row.correlation_id, UUID)
    assert row.occurred_at is not None
    stored = {column.name: getattr(row, column.name) for column in AuditEvent.__table__.columns}
    assert set(stored) == {
        "id",
        "action",
        "actor_user_id",
        "target_user_id",
        "result",
        "reason",
        "occurred_at",
        "correlation_id",
    }
    for secret in (
        token,
        old_hash,
        "private-new-password-hash",
        "private-audit@example.com",
        "private_audit",
    ):
        assert secret not in str(stored)


@pytest.mark.asyncio
async def test_rejected_logout_or_admin_request_never_records_success(
    client, db_session, monkeypatch
):
    user = await _create_user(db_session, email="audit-reject@example.com", username="audit_reject")
    other = await _create_user(db_session, email="audit-other@example.com", username="audit_other")
    access, _ = await _tokens(db_session, user)
    _, other_tokens = await _tokens(db_session, other)
    other_id = other.id
    monkeypatch.setattr(session_module, "AsyncSessionLocal", lambda: db_session)
    app.dependency_overrides[get_db] = get_db
    rejected = await client.post(
        "/api/v1/auth/logout", headers=_bearer(access), json={"refresh_token": other_tokens[0]}
    )
    assert rejected.status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=_bearer(access))).status_code == 200
    rejected_admin = await client.post(
        f"/api/v1/admin/users/{other_id}/deactivate", headers=_bearer(access)
    )
    assert rejected_admin.status_code == 403
    assert (await db_session.scalars(select(AuditEvent))).all() == []
    assert (await db_session.scalars(select(RevokedToken))).all() == []


@pytest.mark.asyncio
async def test_account_deletion_removes_audit_identity_links_without_erasing_the_event(db_session):
    user = await _create_user(
        db_session, email="audit-erasure@example.com", username="audit_erasure"
    )
    audit = await record_audit_event(
        db_session,
        action=AuditAction.PASSWORD_CHANGE,
        actor_user_id=user.id,
        target_user_id=user.id,
        reason=AuditReason.AUTHENTICATED_CHANGE,
    )
    await db_session.commit()
    audit_id, user_id = audit.id, user.id
    await db_session.execute(text("PRAGMA foreign_keys=ON"))
    assert await db_session.scalar(text("PRAGMA foreign_keys")) == 1
    try:
        await db_session.execute(delete(User).where(User.id == user_id))
        await db_session.commit()
        db_session.expire_all()
        retained = await db_session.get(AuditEvent, audit_id)
        assert retained is not None
        assert retained.actor_user_id is None
        assert retained.target_user_id is None
        assert retained.reason == "authenticated_change"
    finally:
        await db_session.rollback()
        await db_session.execute(text("PRAGMA foreign_keys=OFF"))
