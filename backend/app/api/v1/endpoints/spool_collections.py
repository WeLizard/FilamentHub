"""Grouped shelf and personal folders; registered before /spools/{spool_id}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import ERR_SPOOL_FEED_FILTER_INVALID, raise_error
from app.db.session import get_db
from app.models.user import User
from app.models.user_spool import UserSpoolState
from app.schemas.spool import (
    SpoolCollectionMembersUpdate,
    SpoolCollectionName,
    SpoolCollectionResponse,
    SpoolGroupFeedResponse,
)
from app.services.spool_group_service import (
    create_collection,
    delete_collection,
    list_collections,
    list_spool_groups,
    rename_collection,
    update_members,
)

router = APIRouter(prefix="/spools", tags=["spool-collections"])


@router.get("/groups", response_model=SpoolGroupFeedResponse)
async def get_spool_groups(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    state: Annotated[UserSpoolState | None, Query()] = None,
    state_group: Annotated[str | None, Query(pattern="^(available|archived)$")] = None,
    collection_id: Annotated[int | None, Query(ge=1)] = None,
    no_collection: bool = False,
    group_by: Annotated[str, Query(pattern="^(product|brand|type)$")] = "product",
) -> SpoolGroupFeedResponse:
    """Spools grouped by catalog material; expand one group with /feed?group_key=."""
    if (state is not None and state_group is not None) or (
        collection_id is not None and no_collection
    ):
        raise_error(422, ERR_SPOOL_FEED_FILTER_INVALID)
    return await list_spool_groups(
        db,
        current_user.id,
        limit=limit,
        cursor=cursor,
        state=state,
        state_group=state_group,
        collection_id=collection_id,
        no_collection=no_collection,
        group_by=group_by,
    )


@router.get("/collections", response_model=list[SpoolCollectionResponse])
async def get_collections(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SpoolCollectionResponse]:
    return await list_collections(db, current_user.id)


@router.post(
    "/collections", response_model=SpoolCollectionResponse, status_code=status.HTTP_201_CREATED
)
async def post_collection(
    payload: SpoolCollectionName,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolCollectionResponse:
    return await create_collection(db, current_user.id, payload.name)


@router.patch("/collections/{collection_id}", response_model=SpoolCollectionResponse)
async def patch_collection(
    collection_id: int,
    payload: SpoolCollectionName,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolCollectionResponse:
    return await rename_collection(db, current_user.id, collection_id, payload.name)


@router.delete(
    "/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def remove_collection(
    collection_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    await delete_collection(db, current_user.id, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections/{collection_id}/members", response_model=SpoolCollectionResponse)
async def post_collection_members(
    collection_id: int,
    payload: SpoolCollectionMembersUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolCollectionResponse:
    return await update_members(db, current_user.id, collection_id, payload.add, payload.remove)
