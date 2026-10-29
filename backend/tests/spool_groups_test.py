"""Grouped shelf and personal folders: separate spools, honest totals, owner-scoped links."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState


async def _material(db: AsyncSession, slug: str, name: str = "Same name PLA") -> Filament:
    brand = Brand(name=f"Brand {slug}", slug=f"brand-{slug}", active=True)
    filament = Filament(brand=brand, name=name, slug=slug, material_type="PLA", active=True)
    db.add_all([brand, filament])
    await db.flush()
    return filament


_clock = itertools.count()


def _spool(user_id: int, filament_id: int | None, used: float = 0.0, **extra) -> UserSpool:
    # Distinct, microsecond-precise creation times: SQLite's default is whole seconds.
    created = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=next(_clock))
    return UserSpool(
        created_at=created,
        user_id=user_id,
        filament_id=filament_id,
        initial_weight_g=extra.pop("initial", 1000),
        used_weight_g=used,
        state=extra.pop("state", UserSpoolState.shelf),
        source="manual",
        **extra,
    )


@pytest.mark.asyncio
async def test_many_identical_spools_form_one_group_with_exact_totals(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    first = await _material(db_session, "grp-a")
    second = await _material(db_session, "grp-b")  # same display name, different SKU
    db_session.add_all([_spool(auth_user.id, first.id, used=100) for _ in range(30)])
    db_session.add_all([_spool(auth_user.id, second.id), _spool(auth_user.id, None)])
    db_session.add(_spool(auth_user.id, first.id, state=UserSpoolState.archived))
    db_session.add(_spool(auth_user.id, first.id, initial=0))  # size unknown
    await db_session.commit()

    body = (await auth_client.get("/api/v1/spools/groups", params={"limit": 1})).json()
    assert body["summary"]["group_count"] == 3  # two SKUs plus the uncarded bucket
    assert body["summary"]["total"] == 34
    assert len(body["items"]) == 1 and body["next_cursor"]
    page_two = (
        await auth_client.get("/api/v1/spools/groups", params={"limit": 1, "cursor": body["next_cursor"]})
    ).json()
    keys = [item["key"] for item in body["items"] + page_two["items"]]
    assert len(keys) == len(set(keys)) == 3 and page_two["next_cursor"] is None

    big = next(item for item in body["items"] + page_two["items"] if item["key"] == f"f:{first.id}")
    assert big["spool_count"] == 32
    # 30 spools x 900 g known; the archived one and the unknown-size one add nothing.
    assert big["available_remaining_weight_g"] == 27000
    assert big["unknown_mass_count"] == 1
    assert big["state_counts"]["archived"] == 1

    expanded = (
        await auth_client.get("/api/v1/spools/feed", params={"group_key": f"f:{first.id}", "limit": 50})
    ).json()
    assert expanded["summary"]["total"] == 32
    assert (await auth_client.get("/api/v1/spools/feed", params={"group_key": "x:1"})).status_code == 422


@pytest.mark.asyncio
async def test_a_spool_in_two_folders_is_counted_once_and_deleting_a_folder_keeps_it(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    material = await _material(db_session, "folder-a")
    spools = [_spool(auth_user.id, material.id, used=500) for _ in range(3)]
    db_session.add_all(spools)
    await db_session.commit()
    ids = [spool.id for spool in spools]

    blue = (await auth_client.post("/api/v1/spools/collections", json={"name": "Blue"})).json()
    mock = (await auth_client.post("/api/v1/spools/collections", json={"name": "Mockups"})).json()
    duplicate = await auth_client.post("/api/v1/spools/collections", json={"name": "blue"})
    assert duplicate.status_code == 409

    await auth_client.post(f"/api/v1/spools/collections/{blue['id']}/members", json={"add": ids[:2]})
    await auth_client.post(f"/api/v1/spools/collections/{mock['id']}/members", json={"add": ids[1:]})
    # Repeating an add changes nothing.
    again = await auth_client.post(f"/api/v1/spools/collections/{blue['id']}/members", json={"add": ids[:2]})
    assert again.json()["spool_count"] == 2

    everything = (await auth_client.get("/api/v1/spools/groups")).json()["summary"]
    assert everything["total"] == 3 and everything["available_remaining_weight_g"] == 1500
    in_blue = (await auth_client.get("/api/v1/spools/groups", params={"collection_id": blue["id"]})).json()
    assert in_blue["summary"]["total"] == 2 and in_blue["items"][0]["spool_count"] == 2
    unfiled = (await auth_client.get("/api/v1/spools/groups", params={"no_collection": True})).json()
    assert unfiled["summary"]["total"] == 0
    feed = (await auth_client.get("/api/v1/spools/feed")).json()["items"]
    assert sorted(len(item["collection_ids"]) for item in feed) == [1, 1, 2]

    assert (await auth_client.delete(f"/api/v1/spools/collections/{blue['id']}")).status_code == 204
    after = (await auth_client.get("/api/v1/spools/groups")).json()["summary"]
    assert after["total"] == 3
    unfiled = (await auth_client.get("/api/v1/spools/groups", params={"no_collection": True})).json()
    assert unfiled["summary"]["total"] == 1


@pytest.mark.asyncio
async def test_folders_never_touch_another_owners_spools_or_folders(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    material = await _material(db_session, "folder-b")
    foreign = User(email="folders-foreign@example.com", username="folders_foreign",
                   password_hash="unused", active=True)
    db_session.add(foreign)
    await db_session.flush()
    mine, theirs = _spool(auth_user.id, material.id), _spool(foreign.id, material.id)
    db_session.add_all([mine, theirs])
    await db_session.commit()

    folder = (await auth_client.post("/api/v1/spools/collections", json={"name": "Mine"})).json()
    mixed = await auth_client.post(
        f"/api/v1/spools/collections/{folder['id']}/members", json={"add": [mine.id, theirs.id]}
    )
    assert mixed.status_code == 404
    listed = (await auth_client.get("/api/v1/spools/collections")).json()
    assert listed[0]["spool_count"] == 0  # the whole request was refused, mine included

    fake = await auth_client.post("/api/v1/spools/collections/99999/members", json={"add": [mine.id]})
    assert fake.status_code == 404


@pytest.mark.asyncio
async def test_shelf_folds_by_manufacturer_and_type_and_lists_uncarded_spools_last(
    auth_client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    acme = Brand(name="Acme", slug="acme-fold", active=True)
    zed = Brand(name="Zed", slug="zed-fold", active=True)
    pla_red = Filament(brand=acme, name="Red", slug="red", material_type="PLA", active=True)
    pla_blue = Filament(brand=acme, name="Blue", slug="blue", material_type="PLA Matte", active=True)
    petg = Filament(brand=zed, name="Clear", slug="clear", material_type="PETG", active=True)
    for item in (pla_red, pla_blue, petg):
        item.base_material_type = "PETG" if item is petg else "PLA"
    db_session.add_all([acme, zed, pla_red, pla_blue, petg])
    await db_session.flush()
    # The uncarded spool is the newest one, yet must still come last.
    db_session.add_all(
        [
            _spool(auth_user.id, pla_red.id),
            _spool(auth_user.id, pla_red.id, state=UserSpoolState.archived),
            _spool(auth_user.id, pla_blue.id),
            _spool(auth_user.id, petg.id),
            _spool(auth_user.id, None),
        ]
    )
    await db_session.commit()

    async def fetch(mode: str, **extra):
        response = await auth_client.get(
            "/api/v1/spools/groups", params={"group_by": mode, "limit": 1, **extra}
        )
        assert response.status_code == 200, response.json()
        return response.json()

    by_brand = await fetch("brand")
    assert by_brand["summary"]["group_count"] == 3 and by_brand["summary"]["total"] == 5
    assert by_brand["next_cursor"]
    pages = [by_brand]
    while pages[-1]["next_cursor"]:
        pages.append(await fetch("brand", cursor=pages[-1]["next_cursor"]))
    keys = [item["key"] for page in pages for item in page["items"]]
    assert len(keys) == len(set(keys)) == 3 and keys[-1] == "b:0"
    assert {item["key"]: item["spool_count"] for page in pages for item in page["items"]} == {
        f"b:{acme.id}": 3,
        f"b:{zed.id}": 1,
        "b:0": 1,
    }

    by_type = await fetch("type", limit=10)
    assert {item["key"]: item["spool_count"] for item in by_type["items"]} == {
        "t:PLA": 3,
        "t:PETG": 1,
        "t:_none": 1,
    }
    assert by_type["items"][-1]["key"] == "t:_none"

    product = await fetch("product", limit=10)
    assert product["items"][-1]["key"] == "n:0"

    # Each key opens exactly its own spools, and archived ones stay countable.
    for key, expected in ((f"b:{acme.id}", 3), ("t:PLA", 3), ("t:_none", 1), ("b:0", 1), ("n:0", 1)):
        feed = (await auth_client.get("/api/v1/spools/feed", params={"group_key": key})).json()
        assert feed["summary"]["total"] == expected, key
    # Filters still apply inside a fold, and totals count each spool once.
    available = await fetch("type", limit=10, state_group="available")
    assert available["summary"]["total"] == 4
    assert (await auth_client.get("/api/v1/spools/groups", params={"group_by": "x"})).status_code == 422
