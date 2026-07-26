"""A spool's consumption has to be traceable, not just counted."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


async def _spool(db: AsyncSession, user_id: int) -> UserSpool:
    spool = UserSpool(
        user_id=user_id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.active,
        source="manual",
    )
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return spool


@pytest.mark.asyncio
async def test_writing_off_by_hand_leaves_a_record(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    spool = await _spool(db_session, auth_user.id)

    used = await auth_client.post(
        f"/api/v1/spools/{spool.id}/use", json={"delta_weight_g": 120}
    )
    assert used.status_code == 200

    history = await auth_client.get(f"/api/v1/spools/{spool.id}/usage")
    assert history.status_code == 200
    events = history.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "manual_adjust"
    assert events[0]["delta_weight_g"] == 120
    # Without the remaining weight the history cannot be read without replaying
    # every earlier row.
    assert events[0]["remaining_weight_g"] == 880
    assert events[0]["device_name"] is None


@pytest.mark.asyncio
async def test_history_belongs_to_its_owner(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    stranger = User(
        email="usage-stranger@example.com",
        username="usage_stranger",
        password_hash="$2b$12$test",
        active=True,
    )
    db_session.add(stranger)
    await db_session.commit()
    await db_session.refresh(stranger)
    spool = await _spool(db_session, stranger.id)

    hidden = await auth_client.get(f"/api/v1/spools/{spool.id}/usage")
    assert hidden.status_code == 404


@pytest.mark.asyncio
async def test_reverting_gives_the_grams_back_once(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    """A wrong write-off has to be undoable, and only once."""
    spool = await _spool(db_session, auth_user.id)
    await auth_client.post(f"/api/v1/spools/{spool.id}/use", json={"delta_weight_g": 200})
    event_id = (await auth_client.get(f"/api/v1/spools/{spool.id}/usage")).json()[0]["id"]

    reverted = await auth_client.post(
        f"/api/v1/spools/{spool.id}/usage/{event_id}/revert"
    )
    assert reverted.status_code == 200
    assert reverted.json()["delta_weight_g"] == -200
    assert reverted.json()["remaining_weight_g"] == 1000

    await db_session.refresh(spool)
    assert spool.used_weight_g == 0

    again = await auth_client.post(f"/api/v1/spools/{spool.id}/usage/{event_id}/revert")
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "ERR_USAGE_EVENT_ALREADY_REVERTED"
    await db_session.refresh(spool)
    assert spool.used_weight_g == 0
