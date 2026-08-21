"""Authorization and audit boundaries for rare manually granted achievements."""

from sqlalchemy import select

from app.core.errors import (
    ERR_ACHIEVEMENT_ALREADY_AWARDED,
    ERR_ACHIEVEMENT_NOT_MANUAL,
    ERR_ACHIEVEMENT_REGRANT_FORBIDDEN,
)
from app.models.user_achievement import UserAchievement
from app.services.achievement_service import (
    FIRST_PROFILE,
    PROJECT_SUPPORTER,
    read_achievement_overview,
)


async def test_regular_user_cannot_manage_achievements(auth_client, auth_user):
    response = await auth_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": PROJECT_SUPPORTER, "reason": "Helpful project support"},
    )

    assert response.status_code == 403


async def test_manual_achievement_keeps_admin_provenance_and_revocation_history(
    admin_client,
    admin_user,
    auth_user,
    db_session,
):
    blank_reason = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": PROJECT_SUPPORTER, "reason": "   "},
    )
    assert blank_reason.status_code == 422

    automatic = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": FIRST_PROFILE, "reason": "Do not override automatic facts"},
    )
    assert automatic.status_code == 409
    assert automatic.json()["detail"]["code"] == ERR_ACHIEVEMENT_NOT_MANUAL

    automatic_revoke = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements/{FIRST_PROFILE}/revoke",
        json={"reason": "Do not override automatic facts"},
    )
    assert automatic_revoke.status_code == 409
    assert automatic_revoke.json()["detail"]["code"] == ERR_ACHIEVEMENT_NOT_MANUAL

    granted = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": PROJECT_SUPPORTER, "reason": "Supported the project infrastructure"},
    )
    assert granted.status_code == 200
    active = next(
        item for item in granted.json()["achievements"] if item["code"] == PROJECT_SUPPORTER
    )
    assert active["source"] == "manual"
    assert active["awarded_by_user_id"] == admin_user.id
    assert active["award_reason"] == "Supported the project infrastructure"
    assert active["revoked_at"] is None

    duplicate = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": PROJECT_SUPPORTER, "reason": "A duplicate must not replace provenance"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == ERR_ACHIEVEMENT_ALREADY_AWARDED

    revoked = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements/{PROJECT_SUPPORTER}/revoke",
        json={"reason": "The original grant was issued to the wrong account"},
    )
    assert revoked.status_code == 200
    historical = next(
        item for item in revoked.json()["achievements"] if item["code"] == PROJECT_SUPPORTER
    )
    assert historical["revoked_at"] is not None
    assert historical["revoked_by_user_id"] == admin_user.id
    assert historical["revoke_reason"] == "The original grant was issued to the wrong account"

    row = await db_session.scalar(
        select(UserAchievement).where(
            UserAchievement.user_id == auth_user.id,
            UserAchievement.code == PROJECT_SUPPORTER,
        )
    )
    assert row is not None
    assert row.awarded_by_user_id == admin_user.id
    assert row.revoked_at is not None
    public_overview = await read_achievement_overview(db_session, user_id=auth_user.id)
    assert PROJECT_SUPPORTER not in {item.code for item in public_overview.achievements}

    regrant = await admin_client.post(
        f"/api/v1/admin/users/{auth_user.id}/achievements",
        json={"code": PROJECT_SUPPORTER, "reason": "Do not erase the earlier audit trail"},
    )
    assert regrant.status_code == 409
    assert regrant.json()["detail"]["code"] == ERR_ACHIEVEMENT_REGRANT_FORBIDDEN
