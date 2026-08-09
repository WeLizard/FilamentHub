"""Versioned Wiki authoring, peer validation, and moderation endpoints."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_active_user, get_current_active_user_optional
from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_ARTICLE_NOT_FOUND,
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_WIKI_MEDIA_NOT_FOUND,
    raise_error,
)
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.models.wiki_article import WikiArticle
from app.models.wiki_revision import (
    WikiRevision,
    WikiRevisionReview,
    WikiRevisionStatus,
)
from app.models.wiki_space import WikiSpace
from app.schemas.wiki_authoring import (
    WikiArticleDraftCreate,
    WikiMediaUploadResponse,
    WikiModerationDecision,
    WikiPublicRevisionListResponse,
    WikiPublicRevisionResponse,
    WikiRevisionCreate,
    WikiRevisionListResponse,
    WikiRevisionResponse,
    WikiRevisionReviewCreate,
    WikiRevisionReviewResponse,
    WikiRevisionSubmit,
    WikiRevisionUpdate,
    WikiSpaceResponse,
)
from app.services.file_service import WIKI_IMAGE_ALLOWED_EXTENSIONS
from app.services.wiki_media_service import (
    WIKI_MEDIA_MAX_UPLOAD_BYTES,
    can_view_wiki_media,
    create_wiki_media_asset,
    get_wiki_media_asset,
    resolve_wiki_media_path,
    wiki_media_url,
)
from app.services.wiki_revision_service import (
    add_peer_review,
    create_article_with_revision,
    create_revision,
    is_wiki_editor,
    load_revision,
    moderate_revision,
    retry_rejected_revision,
    submit_owned_draft,
    update_owned_draft,
    withdraw_owned_revision,
)

router = APIRouter(prefix="/wiki", tags=["wiki-authoring"])
logger = logging.getLogger(__name__)


async def get_current_wiki_editor(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not is_wiki_editor(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    return current_user


def _revision_response(revision: WikiRevision) -> WikiRevisionResponse:
    article = revision.article
    return WikiRevisionResponse(
        id=revision.id,
        article_id=article.id,
        article_category_id=article.category_id,
        article_slug=article.slug,
        article_title=article.title,
        article_space_key=article.space.key,
        article_language=article.language,
        article_provenance=article.provenance,
        revision_number=revision.revision_number,
        base_revision_id=revision.base_revision_id,
        base_title=(revision.base_revision.title if revision.base_revision else None),
        base_summary=(revision.base_revision.summary if revision.base_revision else None),
        base_content=(revision.base_revision.content if revision.base_revision else None),
        base_tags=(revision.base_revision.tags if revision.base_revision else None),
        created_by_id=revision.created_by_id,
        created_by_username=(
            revision.created_by.username if revision.created_by is not None else None
        ),
        reviewed_by_id=revision.reviewed_by_id,
        reviewed_by_username=(
            revision.reviewed_by.username if revision.reviewed_by is not None else None
        ),
        status=revision.status,
        authorship=revision.authorship,
        title=revision.title,
        summary=revision.summary,
        content=revision.content,
        tags=revision.tags,
        edit_summary=revision.edit_summary,
        review_note=revision.review_note,
        submitted_at=revision.submitted_at,
        reviewed_at=revision.reviewed_at,
        published_at=revision.published_at,
        created_at=revision.created_at,
        updated_at=revision.updated_at,
        peer_reviews=[
            WikiRevisionReviewResponse(
                id=review.id,
                reviewer_id=review.reviewer_id,
                reviewer_username=(
                    review.reviewer.username if review.reviewer is not None else None
                ),
                verdict=review.verdict,
                comment=review.comment,
                evidence_url=review.evidence_url,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            for review in sorted(revision.peer_reviews, key=lambda item: item.created_at)
        ],
    )


def _public_revision_response(revision: WikiRevision) -> WikiPublicRevisionResponse:
    """Serialize only published attribution and content, never review internals."""

    return WikiPublicRevisionResponse(
        id=revision.id,
        revision_number=revision.revision_number,
        base_revision_id=revision.base_revision_id,
        created_by_username=(
            revision.created_by.username if revision.created_by is not None else None
        ),
        authorship=revision.authorship,
        title=revision.title,
        summary=revision.summary,
        content=revision.content,
        tags=revision.tags,
        edit_summary=revision.edit_summary,
        published_at=revision.published_at,
        created_at=revision.created_at,
        updated_at=revision.updated_at,
    )


def _revision_load_options():
    return (
        selectinload(WikiRevision.article).selectinload(WikiArticle.space),
        selectinload(WikiRevision.base_revision),
        selectinload(WikiRevision.created_by),
        selectinload(WikiRevision.reviewed_by),
        selectinload(WikiRevision.peer_reviews).selectinload(
            WikiRevisionReview.reviewer
        ),
    )


async def _revision_page(
    db: AsyncSession,
    statement,
    *,
    page: int,
    page_size: int,
) -> WikiRevisionListResponse:
    count_result = await db.execute(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    total = int(count_result.scalar_one())
    result = await db.execute(
        statement.options(*_revision_load_options())
        .order_by(WikiRevision.updated_at.desc(), WikiRevision.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_revision_response(item) for item in result.scalars().unique().all()]
    return WikiRevisionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/spaces", response_model=list[WikiSpaceResponse])
async def list_wiki_spaces(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WikiSpaceResponse]:
    result = await db.execute(select(WikiSpace).order_by(WikiSpace.order, WikiSpace.id))
    return [
        WikiSpaceResponse(
            key=space.key,
            order=space.order,
            allows_community_authors=space.allows_community_authors,
        )
        for space in result.scalars().all()
    ]


@router.post(
    "/author/media",
    response_model=WikiMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("20/hour")
async def upload_wiki_media(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    file: UploadFile = File(...),
) -> WikiMediaUploadResponse:
    """Normalize a user image to static WebP before it ever reaches storage."""

    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in WIKI_IMAGE_ALLOWED_EXTENSIONS:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_FILE_EXT_NOT_ALLOWED,
            {
                "ext": file_ext,
                "allowed": ", ".join(sorted(WIKI_IMAGE_ALLOWED_EXTENSIONS)),
            },
        )

    try:
        content = await file.read(WIKI_MEDIA_MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(content) > WIKI_MEDIA_MAX_UPLOAD_BYTES:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_FILE_SIZE_EXCEEDED,
            {
                "size_mb": f">{WIKI_MEDIA_MAX_UPLOAD_BYTES / (1024 * 1024):.0f}",
                "max_mb": f"{WIKI_MEDIA_MAX_UPLOAD_BYTES / (1024 * 1024):.0f}",
            },
        )

    asset = await create_wiki_media_asset(
        db,
        user=current_user,
        content=content,
        file_ext=file_ext,
    )
    await db.commit()
    return WikiMediaUploadResponse(
        id=asset.public_id,
        url=wiki_media_url(asset.public_id),
        width=asset.width,
        height=asset.height,
        size_bytes=asset.size_bytes,
    )


@router.get("/media/{public_id}.webp", response_class=FileResponse)
async def read_wiki_media(
    public_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[
        User | None, Depends(get_current_active_user_optional)
    ] = None,
) -> FileResponse:
    """Serve published media publicly and staged media only to its author/editors."""

    asset = await get_wiki_media_asset(db, public_id)
    if not can_view_wiki_media(asset, current_user):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_MEDIA_NOT_FOUND)
    file_path = resolve_wiki_media_path(asset.storage_path)
    if not file_path.is_file():
        logger.error("Wiki media file missing public_id=%s", public_id)
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_MEDIA_NOT_FOUND)

    cache_control = (
        "public, max-age=31536000, immutable"
        if asset.published
        else "private, no-store"
    )
    return FileResponse(
        file_path,
        media_type="image/webp",
        headers={
            "Cache-Control": cache_control,
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/author/articles",
    response_model=WikiRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
async def create_authored_article(
    request: Request,
    data: WikiArticleDraftCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await create_article_with_revision(
        db,
        user=current_user,
        **data.model_dump(),
    )
    return _revision_response(revision)


@router.post(
    "/author/articles/{article_id}/revisions",
    response_model=WikiRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/hour")
async def create_authored_revision(
    request: Request,
    article_id: int,
    data: WikiRevisionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await create_revision(
        db,
        article_id=article_id,
        user=current_user,
        changes=data.model_dump(exclude_unset=True),
    )
    return _revision_response(revision)


@router.get("/author/revisions", response_model=WikiRevisionListResponse)
async def list_own_revisions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    revision_status: WikiRevisionStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> WikiRevisionListResponse:
    statement = select(WikiRevision).where(
        WikiRevision.created_by_id == current_user.id
    )
    if revision_status is not None:
        statement = statement.where(WikiRevision.status == revision_status)
    return await _revision_page(db, statement, page=page, page_size=page_size)


@router.get("/author/revisions/{revision_id}", response_model=WikiRevisionResponse)
async def get_own_revision(
    revision_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await load_revision(db, revision_id)
    if revision.created_by_id != current_user.id and not is_wiki_editor(current_user):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    return _revision_response(revision)


@router.get("/revisions/reviewable", response_model=WikiRevisionListResponse)
async def list_reviewable_revisions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> WikiRevisionListResponse:
    """List submitted revisions the current user has not reviewed or authored."""

    already_reviewed = (
        select(WikiRevisionReview.id)
        .where(
            WikiRevisionReview.revision_id == WikiRevision.id,
            WikiRevisionReview.reviewer_id == current_user.id,
        )
        .exists()
    )
    statement = select(WikiRevision).where(
        WikiRevision.status == WikiRevisionStatus.PENDING_REVIEW,
        or_(
            WikiRevision.created_by_id.is_(None),
            WikiRevision.created_by_id != current_user.id,
        ),
        ~already_reviewed,
    )
    return await _revision_page(db, statement, page=page, page_size=page_size)


@router.patch("/author/revisions/{revision_id}", response_model=WikiRevisionResponse)
async def update_own_revision(
    revision_id: int,
    data: WikiRevisionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await update_owned_draft(
        db,
        revision_id=revision_id,
        user=current_user,
        changes=data.model_dump(exclude_unset=True),
    )
    return _revision_response(revision)


@router.post(
    "/author/revisions/{revision_id}/submit", response_model=WikiRevisionResponse
)
@limiter.limit("30/hour")
async def submit_revision(
    request: Request,
    revision_id: int,
    data: WikiRevisionSubmit,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await submit_owned_draft(
        db,
        revision_id=revision_id,
        user=current_user,
        edit_summary=data.edit_summary,
    )
    return _revision_response(revision)


@router.post(
    "/author/revisions/{revision_id}/withdraw", response_model=WikiRevisionResponse
)
async def withdraw_revision(
    revision_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await withdraw_owned_revision(
        db, revision_id=revision_id, user=current_user
    )
    return _revision_response(revision)


@router.post(
    "/author/revisions/{revision_id}/retry", response_model=WikiRevisionResponse
)
@limiter.limit("20/hour")
async def retry_revision(
    request: Request,
    revision_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await retry_rejected_revision(
        db,
        revision_id=revision_id,
        user=current_user,
    )
    return _revision_response(revision)


@router.post(
    "/revisions/{revision_id}/reviews", response_model=WikiRevisionResponse
)
@limiter.limit("60/hour")
async def review_revision(
    request: Request,
    revision_id: int,
    data: WikiRevisionReviewCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> WikiRevisionResponse:
    revision = await add_peer_review(
        db,
        revision_id=revision_id,
        user=current_user,
        **data.model_dump(),
    )
    return _revision_response(revision)


@router.get("/moderation/revisions", response_model=WikiRevisionListResponse)
async def list_moderation_queue(
    db: Annotated[AsyncSession, Depends(get_db)],
    _editor: Annotated[User, Depends(get_current_wiki_editor)],
    revision_status: WikiRevisionStatus = Query(
        WikiRevisionStatus.PENDING_REVIEW, alias="status"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> WikiRevisionListResponse:
    return await _revision_page(
        db,
        select(WikiRevision).where(WikiRevision.status == revision_status),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/moderation/revisions/{revision_id}", response_model=WikiRevisionResponse
)
async def get_moderation_revision(
    revision_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _editor: Annotated[User, Depends(get_current_wiki_editor)],
) -> WikiRevisionResponse:
    return _revision_response(await load_revision(db, revision_id))


@router.post(
    "/moderation/revisions/{revision_id}/decision",
    response_model=WikiRevisionResponse,
)
async def decide_revision(
    revision_id: int,
    data: WikiModerationDecision,
    db: Annotated[AsyncSession, Depends(get_db)],
    editor: Annotated[User, Depends(get_current_wiki_editor)],
) -> WikiRevisionResponse:
    revision = await moderate_revision(
        db,
        revision_id=revision_id,
        editor=editor,
        decision=data.decision,
        review_note=data.review_note,
    )
    return _revision_response(revision)


@router.get(
    "/articles/{article_slug}/history", response_model=WikiPublicRevisionListResponse
)
async def list_public_revision_history(
    article_slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> WikiPublicRevisionListResponse:
    article_id = (
        await db.execute(
            select(WikiArticle.id).where(
                WikiArticle.slug == article_slug,
                WikiArticle.published.is_(True),
            )
        )
    ).scalar_one_or_none()
    if article_id is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ARTICLE_NOT_FOUND)
    statement = select(WikiRevision).where(
        WikiRevision.article_id == article_id,
        WikiRevision.status == WikiRevisionStatus.PUBLISHED,
    )
    count_result = await db.execute(
        select(func.count()).select_from(statement.order_by(None).subquery())
    )
    total = int(count_result.scalar_one())
    result = await db.execute(
        statement.options(
            selectinload(WikiRevision.created_by),
        )
        .order_by(WikiRevision.revision_number.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return WikiPublicRevisionListResponse(
        items=[_public_revision_response(item) for item in result.scalars().all()],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )
