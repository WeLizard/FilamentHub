"""Edge nodes: the owner registers and manages them; a node activates and reports itself."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.limiter import client_key, edge_node_token_key, limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.edge_node import (
    EdgeNodeActivateRequest,
    EdgeNodeActivateResponse,
    EdgeNodeHeartbeatRequest,
    EdgeNodeHeartbeatResponse,
    EdgeNodePairingCreate,
    EdgeNodePairingResponse,
    EdgeNodePairingStatus,
    EdgeNodeRename,
    EdgeNodeResponse,
)
from app.services.edge_node_service import (
    activate_edge_node,
    get_edge_node_pairing_status,
    issue_edge_node_pairing,
    list_edge_nodes,
    record_edge_node_heartbeat,
    remove_edge_node,
    rename_edge_node,
    require_edge_node_token,
)

router = APIRouter(prefix="/edge/nodes", tags=["edge-nodes"])


@router.get("", response_model=list[EdgeNodeResponse])
async def my_nodes(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[EdgeNodeResponse]:
    return await list_edge_nodes(db, user_id=current_user.id)


@router.post("/pairing", response_model=EdgeNodePairingResponse)
@limiter.limit("10/minute")
async def create_pairing(
    request: Request,
    payload: EdgeNodePairingCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EdgeNodePairingResponse:
    return await issue_edge_node_pairing(db, user_id=current_user.id, payload=payload)


@router.get("/pairing/{pairing_id}", response_model=EdgeNodePairingStatus)
async def pairing_status(
    pairing_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EdgeNodePairingStatus:
    return await get_edge_node_pairing_status(db, user_id=current_user.id, pairing_id=pairing_id)


@router.post("/activate", response_model=EdgeNodeActivateResponse)
@limiter.limit("10/minute")
async def activate(
    request: Request,
    payload: EdgeNodeActivateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EdgeNodeActivateResponse:
    return await activate_edge_node(db, payload)


@router.post("/heartbeat", response_model=EdgeNodeHeartbeatResponse)
@limiter.limit("600/minute", key_func=client_key)
@limiter.limit("6/minute", key_func=edge_node_token_key)
async def heartbeat(
    request: Request,
    payload: EdgeNodeHeartbeatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    node_token: Annotated[str | None, Header(alias="X-FilamentHub-Edge-Token")] = None,
) -> EdgeNodeHeartbeatResponse:
    context = await require_edge_node_token(db, node_token)
    return await record_edge_node_heartbeat(db, context, payload)


@router.patch("/{node_id}", response_model=EdgeNodeResponse)
async def rename(
    node_id: int,
    payload: EdgeNodeRename,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EdgeNodeResponse:
    return await rename_edge_node(db, user_id=current_user.id, node_id=node_id, name=payload.name)


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(
    node_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await remove_edge_node(db, user_id=current_user.id, node_id=node_id)
