"""Feedback conversation API tests."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.notification import Notification
from app.models.user import User
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)

pytestmark = pytest.mark.asyncio


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


async def _create_feedback(client: AsyncClient, user: User) -> int:
    response = await client.post(
        "/api/v1/feedback/",
        headers=_headers(user),
        json={
            "type": "question",
            "subject": "OctoPrint slots",
            "message": "Are these physical gates?",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_feedback_owner_and_admin_can_read_the_thread(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    feedback_id = await _create_feedback(client, auth_user)

    owner_response = await client.get(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(auth_user),
    )
    assert owner_response.status_code == 200
    assert owner_response.json()["messages"] == [
        {
            "id": owner_response.json()["messages"][0]["id"],
            "author_user_id": auth_user.id,
            "author_type": "user",
            "message": "Are these physical gates?",
            "created_at": owner_response.json()["messages"][0]["created_at"],
        }
    ]

    admin_response = await client.get(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(admin_user),
    )
    assert admin_response.status_code == 200

    other_user = User(
        email="other_feedback_user@example.com",
        username="otherfeedbackuser",
        password_hash="$2b$12$test",
        active=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(other_user)
    await db_session.commit()
    await db_session.refresh(other_user)

    forbidden = await client.get(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(other_user),
    )
    assert forbidden.status_code == 404


async def test_feedback_thread_is_ordered_idempotent_and_locked_by_final_status(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    feedback_id = await _create_feedback(client, auth_user)
    admin_key = UUID("2ed3f894-b667-4f9c-a522-92e73e2eae55")

    admin_reply = await client.patch(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(admin_user),
        json={
            "status": "resolved",
            "admin_response": "Please confirm whether this is an MMU.",
            "reply_idempotency_key": str(admin_key),
        },
    )
    assert admin_reply.status_code == 200
    assert [item["author_type"] for item in admin_reply.json()["messages"]] == [
        "user",
        "admin",
    ]

    repeated_admin_reply = await client.patch(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(admin_user),
        json={
            "status": "resolved",
            "admin_response": "Please confirm whether this is an MMU.",
            "reply_idempotency_key": str(admin_key),
        },
    )
    assert repeated_admin_reply.status_code == 200
    assert len(repeated_admin_reply.json()["messages"]) == 2

    notifications = (
        await db_session.execute(
            select(Notification).where(Notification.user_id == auth_user.id)
        )
    ).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].link == f"/feedback/{feedback_id}"

    blocked_reply = await client.post(
        f"/api/v1/feedback/{feedback_id}/messages",
        headers=_headers(auth_user),
        json={
            "message": "It is a physical feeder.",
            "idempotency_key": "38a2f696-62bf-43ae-94ef-476779f29fde",
        },
    )
    assert blocked_reply.status_code == 409
    assert blocked_reply.json()["detail"]["code"] == "ERR_FEEDBACK_THREAD_CLOSED"

    reopened = await client.patch(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(admin_user),
        json={"status": "in_progress"},
    )
    assert reopened.status_code == 200

    user_payload = {
        "message": "It is a physical feeder.",
        "idempotency_key": "38a2f696-62bf-43ae-94ef-476779f29fde",
    }
    user_reply = await client.post(
        f"/api/v1/feedback/{feedback_id}/messages",
        headers=_headers(auth_user),
        json=user_payload,
    )
    assert user_reply.status_code == 200
    assert user_reply.json()["status"] == "open"
    assert [item["message"] for item in user_reply.json()["messages"]] == [
        "Are these physical gates?",
        "Please confirm whether this is an MMU.",
        "It is a physical feeder.",
    ]

    repeated_user_reply = await client.post(
        f"/api/v1/feedback/{feedback_id}/messages",
        headers=_headers(auth_user),
        json=user_payload,
    )
    assert repeated_user_reply.status_code == 200
    assert len(repeated_user_reply.json()["messages"]) == 3

    closed = await client.patch(
        f"/api/v1/feedback/{feedback_id}",
        headers=_headers(admin_user),
        json={
            "status": "closed",
            "admin_response": "Thanks, this conversation is now closed.",
            "reply_idempotency_key": "ec06bd69-60c5-4690-8f29-50257052347e",
        },
    )
    assert closed.status_code == 200
    assert len(closed.json()["messages"]) == 4

    blocked_after_close = await client.post(
        f"/api/v1/feedback/{feedback_id}/messages",
        headers=_headers(auth_user),
        json={
            "message": "One more detail.",
            "idempotency_key": "24a7144e-b3f1-4fbd-8082-ece5f1426ab6",
        },
    )
    assert blocked_after_close.status_code == 409
