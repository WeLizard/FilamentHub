"""Registering an Edge node with an account, and the node's own access afterwards.

A node joins in two steps. Its owner asks for a one-time code; the node then
presents that code together with a secret it generated and already saved. The
server keeps only the digest of that secret. Because the secret exists on the
node before the request, a lost answer is harmless: the same node repeats the
request and gets the same receipt, while the code works for no other secret.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_EDGE_NODE_LIMIT,
    ERR_EDGE_NODE_NOT_FOUND,
    ERR_EDGE_NODE_PAIRING_INVALID,
    ERR_EDGE_NODE_UNAUTHORIZED,
    raise_error,
)
from app.models.edge_node import EdgeNode, EdgeNodeCredential, EdgeNodePairing
from app.schemas.edge_node import (
    EdgeNodeActivateRequest,
    EdgeNodeActivateResponse,
    EdgeNodeHeartbeatRequest,
    EdgeNodeHeartbeatResponse,
    EdgeNodePairingCreate,
    EdgeNodePairingResponse,
    EdgeNodePairingStatus,
    EdgeNodeResponse,
)

PAIRING_TTL = timedelta(minutes=10)
# A used code stays this long so that its node can repeat a lost request.
PAIRING_RETENTION = timedelta(days=1)
MAX_EDGE_NODES = 32
# A node reports once a minute; two missed reports in a row mean it is away.
ONLINE_WINDOW = timedelta(seconds=150)


@dataclass(frozen=True)
class EdgeNodeContext:
    node: EdgeNode
    credential: EdgeNodeCredential


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_pairing_code(value: str) -> str:
    compact = "".join(character for character in value.upper() if character.isalnum())
    return compact[2:] if compact.startswith("FE") else compact


def _new_pairing_code() -> str:
    compact = secrets.token_hex(6).upper()
    return f"FE-{compact[:6]}-{compact[6:]}"


def node_response(node: EdgeNode, now: datetime | None = None) -> EdgeNodeResponse:
    seen = node.last_seen_at
    return EdgeNodeResponse(
        id=node.id,
        name=node.name,
        kind=node.kind,
        kit_id=node.kit_id,
        runtime_version=node.runtime_version,
        created_at=node.created_at,
        last_seen_at=seen,
        online=seen is not None and (now or _now()) - _as_utc(seen) <= ONLINE_WINDOW,
    )


async def _owned_node(db: AsyncSession, user_id: int, node_id: int) -> EdgeNode:
    node = await db.scalar(
        select(EdgeNode).where(EdgeNode.id == node_id, EdgeNode.user_id == user_id)
    )
    if node is None:
        raise_error(404, ERR_EDGE_NODE_NOT_FOUND)
    return node


async def issue_edge_node_pairing(
    db: AsyncSession, *, user_id: int, payload: EdgeNodePairingCreate
) -> EdgeNodePairingResponse:
    now = _now()
    if payload.node_id is not None:
        await _owned_node(db, user_id, payload.node_id)
    else:
        count = await db.scalar(
            select(func.count()).select_from(EdgeNode).where(EdgeNode.user_id == user_id)
        )
        if (count or 0) >= MAX_EDGE_NODES:
            raise_error(409, ERR_EDGE_NODE_LIMIT, params={"limit": MAX_EDGE_NODES})
    # One live code per account: asking again replaces a code that was not used.
    await db.execute(
        delete(EdgeNodePairing).where(
            EdgeNodePairing.user_id == user_id,
            (EdgeNodePairing.consumed_at.is_(None))
            | (EdgeNodePairing.expires_at < now - PAIRING_RETENTION),
        )
    )
    code = _new_pairing_code()
    pairing = EdgeNodePairing(
        user_id=user_id,
        node_id=payload.node_id,
        name=payload.name,
        kind=payload.kind,
        kit_id=payload.kit_id,
        code_hash=_digest(_normalize_pairing_code(code)),
        expires_at=now + PAIRING_TTL,
    )
    db.add(pairing)
    await db.commit()
    return EdgeNodePairingResponse(
        pairing_id=pairing.id, pairing_code=code, expires_at=pairing.expires_at
    )


async def get_edge_node_pairing_status(
    db: AsyncSession, *, user_id: int, pairing_id: int
) -> EdgeNodePairingStatus:
    pairing = await db.scalar(
        select(EdgeNodePairing).where(
            EdgeNodePairing.id == pairing_id, EdgeNodePairing.user_id == user_id
        )
    )
    # A replaced or cleaned-up code reads the same as one that ran out.
    if pairing is None:
        return EdgeNodePairingStatus(state="expired")
    if pairing.consumed_at is not None and pairing.node_id is not None:
        node = await db.get(EdgeNode, pairing.node_id)
        if node is not None:
            return EdgeNodePairingStatus(state="activated", node=node_response(node))
    if pairing.consumed_at is None and _as_utc(pairing.expires_at) >= _now():
        return EdgeNodePairingStatus(state="pending")
    return EdgeNodePairingStatus(state="expired")


async def activate_edge_node(
    db: AsyncSession, payload: EdgeNodeActivateRequest
) -> EdgeNodeActivateResponse:
    proof = _digest(payload.node_token)
    pairing = await db.scalar(
        select(EdgeNodePairing)
        .where(EdgeNodePairing.code_hash == _digest(_normalize_pairing_code(payload.pairing_code)))
        .with_for_update()
    )
    if pairing is None:
        raise_error(401, ERR_EDGE_NODE_PAIRING_INVALID)
    now = _now()

    if pairing.consumed_at is not None:
        # The same node asking again after a lost answer; nobody else.
        node = await db.get(EdgeNode, pairing.node_id) if pairing.node_id else None
        if node is None or not secrets.compare_digest(pairing.proof_hash or "", proof):
            raise_error(401, ERR_EDGE_NODE_PAIRING_INVALID)
        return EdgeNodeActivateResponse(node_id=node.id, name=node.name)
    if _as_utc(pairing.expires_at) < now:
        raise_error(401, ERR_EDGE_NODE_PAIRING_INVALID)

    if pairing.node_id is not None:
        node = await db.get(EdgeNode, pairing.node_id)
        if node is None:
            raise_error(401, ERR_EDGE_NODE_PAIRING_INVALID)
        node.name = pairing.name
    else:
        node = EdgeNode(user_id=pairing.user_id, name=pairing.name, kind=pairing.kind)
        db.add(node)
    node.kind = pairing.kind
    node.kit_id = pairing.kit_id
    node.node_instance_id = payload.node_instance_id
    node.runtime_version = payload.runtime_version
    node.last_seen_at = now
    await db.flush()

    credential = await db.scalar(
        select(EdgeNodeCredential).where(EdgeNodeCredential.node_id == node.id)
    )
    if credential is None:
        db.add(EdgeNodeCredential(node_id=node.id, token_hash=proof, activated_at=now))
    else:
        # Linking again replaces the secret: the previous installation stops working.
        credential.token_hash = proof
        credential.credential_generation = int(credential.credential_generation or 0) + 1
        credential.activated_at = now
    pairing.node_id = node.id
    pairing.consumed_at = now
    pairing.proof_hash = proof
    try:
        await db.commit()
    except IntegrityError:
        # The secret already belongs to another node.
        await db.rollback()
        raise_error(401, ERR_EDGE_NODE_PAIRING_INVALID)
    return EdgeNodeActivateResponse(node_id=node.id, name=node.name)


async def require_edge_node_token(db: AsyncSession, token: str | None) -> EdgeNodeContext:
    if token is None or not token.startswith("fhen_"):
        raise_error(401, ERR_EDGE_NODE_UNAUTHORIZED)
    credential = await db.scalar(
        select(EdgeNodeCredential).where(EdgeNodeCredential.token_hash == _digest(token))
    )
    node = await db.get(EdgeNode, credential.node_id) if credential is not None else None
    if credential is None or node is None:
        raise_error(401, ERR_EDGE_NODE_UNAUTHORIZED)
    return EdgeNodeContext(node=node, credential=credential)


async def record_edge_node_heartbeat(
    db: AsyncSession, context: EdgeNodeContext, payload: EdgeNodeHeartbeatRequest
) -> EdgeNodeHeartbeatResponse:
    now = _now()
    context.node.last_seen_at = now
    if payload.runtime_version is not None:
        context.node.runtime_version = payload.runtime_version
    await db.commit()
    return EdgeNodeHeartbeatResponse(node_id=context.node.id, server_time=now)


async def list_edge_nodes(db: AsyncSession, *, user_id: int) -> list[EdgeNodeResponse]:
    nodes = await db.scalars(
        select(EdgeNode).where(EdgeNode.user_id == user_id).order_by(EdgeNode.id)
    )
    now = _now()
    return [node_response(node, now) for node in nodes]


async def rename_edge_node(
    db: AsyncSession, *, user_id: int, node_id: int, name: str
) -> EdgeNodeResponse:
    node = await _owned_node(db, user_id, node_id)
    node.name = name
    await db.commit()
    return node_response(node)


async def remove_edge_node(db: AsyncSession, *, user_id: int, node_id: int) -> None:
    """Forget the node; its secret stops working at once."""
    node = await _owned_node(db, user_id, node_id)
    await db.delete(node)
    await db.commit()
