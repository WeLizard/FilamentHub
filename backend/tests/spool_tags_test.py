"""Provider-neutral spool tag API and account isolation tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_spool import UserSpool


async def _spool(db: AsyncSession, user_id: int) -> UserSpool:
    spool = UserSpool(user_id=user_id, initial_weight_g=1000.0, source="manual")
    db.add(spool)
    await db.commit()
    await db.refresh(spool)
    return spool


@pytest.mark.asyncio
async def test_user_can_link_normalize_resolve_and_unlink_tag(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    spool = await _spool(db_session, auth_user.id)

    linked = await auth_client.post(
        f"/api/v1/spool-tags/{spool.id}",
        json={"uid": "04:a1-b2 c3", "technology": "nfc", "format": " NTAG-215 "},
    )
    assert linked.status_code == 201
    assert linked.json()["spool_id"] == spool.id
    assert linked.json()["uid"] == "04A1B2C3"
    assert linked.json()["technology"] == "nfc"
    assert linked.json()["format"] == "ntag-215"

    resolved = await auth_client.get("/api/v1/spool-tags/resolve?uid=04A1B2C3")
    assert resolved.status_code == 200
    assert resolved.json() == {
        "uid": "04A1B2C3",
        "status": "matched",
        "spool_id": spool.id,
    }

    listed = await auth_client.get(f"/api/v1/spool-tags?spool_id={spool.id}")
    assert listed.status_code == 200
    assert [item["uid"] for item in listed.json()] == ["04A1B2C3"]

    removed = await auth_client.delete(f"/api/v1/spool-tags/{spool.id}/04:a1:b2:c3")
    assert removed.status_code == 204
    unresolved = await auth_client.get("/api/v1/spool-tags/resolve?uid=04A1B2C3")
    assert unresolved.json() == {
        "uid": "04A1B2C3",
        "status": "unlinked",
        "spool_id": None,
    }


@pytest.mark.asyncio
async def test_tag_uid_is_unique_per_account_and_idempotent_on_same_spool(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    first = await _spool(db_session, auth_user.id)
    second = await _spool(db_session, auth_user.id)

    initial = await auth_client.post(
        f"/api/v1/spool-tags/{first.id}",
        json={"uid": "AABBCCDD", "technology": "nfc"},
    )
    replay = await auth_client.post(
        f"/api/v1/spool-tags/{first.id}",
        json={"uid": "aa-bb-cc-dd", "technology": "nfc"},
    )
    conflict = await auth_client.post(
        f"/api/v1/spool-tags/{second.id}",
        json={"uid": "AABBCCDD", "technology": "nfc"},
    )

    assert initial.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == initial.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {
        "code": "ERR_SPOOL_TAG_CONFLICT",
        "params": {"uid": "AABBCCDD", "spool_id": first.id},
    }


@pytest.mark.asyncio
async def test_tag_bindings_do_not_cross_account_boundary(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    foreign = User(
        email="foreign-tag@example.com",
        username="foreign_tag_user",
        password_hash="not-used",
        active=True,
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)
    foreign_spool = await _spool(db_session, foreign.id)

    link = await auth_client.post(
        f"/api/v1/spool-tags/{foreign_spool.id}",
        json={"uid": "01020304", "technology": "nfc"},
    )
    delete = await auth_client.delete(
        f"/api/v1/spool-tags/{foreign_spool.id}/01020304"
    )

    assert link.status_code == 404
    assert link.json()["detail"]["code"] == "ERR_SPOOL_NOT_ACCESSIBLE"
    assert delete.status_code == 404
    assert delete.json()["detail"]["code"] == "ERR_SPOOL_TAG_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_or_unknown_tag_never_creates_or_links_a_spool(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
) -> None:
    spool = await _spool(db_session, auth_user.id)

    invalid_query = await auth_client.get("/api/v1/spool-tags/resolve?uid=not-a-tag")
    odd_query = await auth_client.get("/api/v1/spool-tags/resolve?uid=ABC")
    invalid_link = await auth_client.post(
        f"/api/v1/spool-tags/{spool.id}",
        json={"uid": "not-a-tag", "technology": "nfc"},
    )
    unknown = await auth_client.get("/api/v1/spool-tags/resolve?uid=DEADBEEF")
    listed = await auth_client.get("/api/v1/spool-tags")

    assert invalid_query.status_code == 400
    assert invalid_query.json()["detail"]["code"] == "ERR_SPOOL_TAG_INVALID"
    assert odd_query.status_code == 400
    assert invalid_link.status_code == 422
    assert unknown.json()["status"] == "unlinked"
    assert listed.json() == []
