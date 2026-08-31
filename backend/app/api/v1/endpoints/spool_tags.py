"""Account-owned physical tag bindings for UserSpool identities."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_SPOOL_NOT_ACCESSIBLE,
    ERR_SPOOL_TAG_CONFLICT,
    ERR_SPOOL_TAG_INVALID,
    ERR_SPOOL_TAG_NOT_FOUND,
    raise_error,
)
from app.core.tag_identity import normalize_tag_uid
from app.db.session import get_db
from app.models.user import User
from app.schemas.spool_tag import (
    SpoolTagCreateRequest,
    SpoolTagResolutionResponse,
    SpoolTagResponse,
)
from app.services.spool_tag_service import (
    SpoolTagConflict,
    find_spool_tag,
    link_spool_tag,
    list_spool_tags,
    unlink_spool_tag,
)

router = APIRouter(prefix="/spool-tags", tags=["spool-tags"])


@router.get("", response_model=list[SpoolTagResponse])
async def get_spool_tags(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    spool_id: Annotated[int | None, Query(ge=1)] = None,
) -> list[SpoolTagResponse]:
    tags = await list_spool_tags(
        db,
        user_id=current_user.id,
        spool_ids=[spool_id] if spool_id is not None else None,
    )
    return [SpoolTagResponse.model_validate(tag) for rows in tags.values() for tag in rows]


@router.get("/resolve", response_model=SpoolTagResolutionResponse)
async def resolve_spool_tag(
    uid: Annotated[str, Query(min_length=1, max_length=128)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolTagResolutionResponse:
    try:
        normalized = normalize_tag_uid(uid)
    except ValueError:
        raise_error(400, ERR_SPOOL_TAG_INVALID)
    tag = await find_spool_tag(db, user_id=current_user.id, uid=normalized)
    return SpoolTagResolutionResponse(
        uid=normalized,
        status="matched" if tag is not None else "unlinked",
        spool_id=tag.spool_id if tag is not None else None,
    )


@router.post(
    "/{spool_id}",
    response_model=SpoolTagResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_spool_tag(
    spool_id: int,
    payload: SpoolTagCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SpoolTagResponse:
    try:
        tag = await link_spool_tag(
            db,
            user_id=current_user.id,
            spool_id=spool_id,
            uid=payload.uid,
            technology=payload.technology,
            tag_format=payload.format,
            source="user",
        )
    except SpoolTagConflict as exc:
        raise_error(
            409,
            ERR_SPOOL_TAG_CONFLICT,
            {"uid": exc.uid, "spool_id": exc.spool_id},
        )
    if tag is None:
        raise_error(404, ERR_SPOOL_NOT_ACCESSIBLE, {"spool_id": spool_id})
    await db.commit()
    await db.refresh(tag)
    return SpoolTagResponse.model_validate(tag)


@router.delete("/{spool_id}/{uid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_spool_tag(
    spool_id: int,
    uid: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        removed = await unlink_spool_tag(
            db,
            user_id=current_user.id,
            spool_id=spool_id,
            uid=uid,
        )
    except ValueError:
        raise_error(400, ERR_SPOOL_TAG_INVALID)
    if not removed:
        raise_error(404, ERR_SPOOL_TAG_NOT_FOUND)
    await db.commit()
