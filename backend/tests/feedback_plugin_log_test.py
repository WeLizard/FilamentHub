"""Plugin log attached to a problem report."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.feedback import Feedback
from app.models.user import User

pytestmark = pytest.mark.asyncio


def _headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


async def _report(client: AsyncClient, user: User, plugin_log: str):
    return await client.post(
        "/api/v1/feedback/",
        headers=_headers(user),
        json={
            "type": "bug",
            "subject": "Sync failed",
            "message": "Red toast after opening the plugin",
            "source": "orca_plugin",
            "plugin_log": plugin_log,
        },
    )


async def test_plugin_log_is_stored_encrypted_and_served_only_as_inert_download(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    response = await _report(
        client,
        auth_user,
        "sync start\r\n\x1b[31mred\x1b[0m ‮evil‬\x00 done",
    )
    assert response.status_code == 201
    expected = "sync start\n[31mred[0m evil done"
    assert response.json()["plugin_log_size"] == len(expected.encode("utf-8"))
    feedback_id = response.json()["id"]

    stored = (
        await db_session.execute(select(Feedback.plugin_log).where(Feedback.id == feedback_id))
    ).scalar_one()
    assert stored is not None
    assert stored.startswith("fh1:")
    assert "sync start" not in stored

    download = await client.get(
        f"/api/v1/feedback/{feedback_id}/plugin-log",
        headers=_headers(admin_user),
    )
    assert download.status_code == 200
    assert download.text == expected
    assert download.headers["content-type"] == "text/plain; charset=utf-8"
    assert download.headers["content-disposition"] == (
        f'attachment; filename="feedback-{feedback_id}-plugin.log"'
    )
    assert download.headers["x-content-type-options"] == "nosniff"

    owner_download = await client.get(
        f"/api/v1/feedback/{feedback_id}/plugin-log",
        headers=_headers(auth_user),
    )
    assert owner_download.status_code == 403


async def test_plugin_log_larger_than_the_attachment_limit_is_rejected(
    client: AsyncClient,
    auth_user: User,
) -> None:
    response = await _report(client, auth_user, "ж" * 40_000)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [("message", "x" * 10_001), ("source", "s" * 51)],
    ids=["message", "source"],
)
async def test_overlong_feedback_fields_are_refused_before_the_database(
    client: AsyncClient,
    auth_user: User,
    field: str,
    value: str,
) -> None:
    payload = {"type": "bug", "subject": "Sync failed", "message": "Details", field: value}
    response = await client.post("/api/v1/feedback/", headers=_headers(auth_user), json=payload)

    assert response.status_code == 422
