"""An Edge node joins an account once, by a one-time code and its own secret."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.edge_node import EdgeNode, EdgeNodePairing
from app.models.user import User

NODES = "/api/v1/edge/nodes"
SECRET = "fhen_" + "a" * 43
OTHER_SECRET = "fhen_" + "b" * 43


def _as(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def _pairing(client: AsyncClient, user: User, **extra) -> dict:
    response = await client.post(
        f"{NODES}/pairing",
        headers=_as(user),
        json={"name": "Workbench", "kind": "esp_kit", "kit_id": "c3-supermini-pn5180", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _activate(client: AsyncClient, code: str, secret: str = SECRET):
    return await client.post(
        f"{NODES}/activate",
        json={"pairing_code": code, "node_token": secret, "runtime_version": "0.2.0"},
    )


async def _heartbeat(client: AsyncClient, secret: str):
    return await client.post(
        f"{NODES}/heartbeat", headers={"X-FilamentHub-Edge-Token": secret}, json={}
    )


@pytest.mark.asyncio
async def test_node_joins_once_and_stops_working_when_removed(
    client: AsyncClient, auth_user: User
) -> None:
    pairing = await _pairing(client, auth_user)
    status = await client.get(f"{NODES}/pairing/{pairing['pairing_id']}", headers=_as(auth_user))
    assert status.json() == {"state": "pending", "node": None}
    # The secret is useless until the code has accepted it.
    assert (await _heartbeat(client, SECRET)).status_code == 401

    activated = await _activate(client, pairing["pairing_code"])
    assert activated.status_code == 200, activated.text
    node_id = activated.json()["node_id"]

    # A lost answer: the same node asks again and gets the same node, not a second one.
    assert (await _activate(client, pairing["pairing_code"])).json()["node_id"] == node_id
    # The code is spent for everybody else.
    assert (await _activate(client, pairing["pairing_code"], OTHER_SECRET)).status_code == 401
    assert (await _heartbeat(client, OTHER_SECRET)).status_code == 401

    status = await client.get(f"{NODES}/pairing/{pairing['pairing_id']}", headers=_as(auth_user))
    assert status.json()["state"] == "activated"
    assert (await _heartbeat(client, SECRET)).status_code == 200
    listed = (await client.get(NODES, headers=_as(auth_user))).json()
    assert [(node["id"], node["name"], node["online"]) for node in listed] == [
        (node_id, "Workbench", True)
    ]

    removed = await client.delete(f"{NODES}/{node_id}", headers=_as(auth_user))
    assert removed.status_code == 204
    assert (await _heartbeat(client, SECRET)).status_code == 401


@pytest.mark.asyncio
async def test_node_belongs_to_the_account_that_issued_the_code(
    client: AsyncClient, auth_user: User, admin_user: User
) -> None:
    pairing = await _pairing(client, auth_user)
    node_id = (await _activate(client, pairing["pairing_code"])).json()["node_id"]

    assert (await client.get(NODES, headers=_as(admin_user))).json() == []
    foreign_status = await client.get(
        f"{NODES}/pairing/{pairing['pairing_id']}", headers=_as(admin_user)
    )
    assert foreign_status.json()["state"] == "expired"
    assert (
        await client.patch(f"{NODES}/{node_id}", headers=_as(admin_user), json={"name": "Mine"})
    ).status_code == 404
    assert (await client.delete(f"{NODES}/{node_id}", headers=_as(admin_user))).status_code == 404
    # Nor may another account aim a new code at this node.
    stolen = await client.post(
        f"{NODES}/pairing",
        headers=_as(admin_user),
        json={"name": "Mine", "kind": "esp_kit", "node_id": node_id},
    )
    assert stolen.status_code == 404
    assert (await _heartbeat(client, SECRET)).status_code == 200


@pytest.mark.asyncio
async def test_expired_or_replaced_code_registers_nothing(
    client: AsyncClient, auth_user: User, db_session: AsyncSession
) -> None:
    first = await _pairing(client, auth_user)
    second = await _pairing(client, auth_user)
    # Asking again replaced the unused code.
    assert (await _activate(client, first["pairing_code"])).status_code == 401

    stored = await db_session.scalar(select(EdgeNodePairing))
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    assert (await _activate(client, second["pairing_code"])).status_code == 401
    assert await db_session.scalar(select(EdgeNode)) is None
    # A printer bridge token is not a node secret.
    assert (await _activate(client, second["pairing_code"], "fhpb_" + "a" * 43)).status_code == 422


@pytest.mark.asyncio
async def test_linking_a_node_again_replaces_its_secret(
    client: AsyncClient, auth_user: User
) -> None:
    node_id = (await _activate(client, (await _pairing(client, auth_user))["pairing_code"])).json()[
        "node_id"
    ]
    again = await _pairing(client, auth_user, node_id=node_id, name="Workbench 2")
    relinked = await _activate(client, again["pairing_code"], OTHER_SECRET)

    assert relinked.json() == {"node_id": node_id, "name": "Workbench 2"}
    assert (await _heartbeat(client, SECRET)).status_code == 401
    assert (await _heartbeat(client, OTHER_SECRET)).status_code == 200
    assert len((await client.get(NODES, headers=_as(auth_user))).json()) == 1
