"""Transactional Wiki authoring, revision, and moderation rules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_ARTICLE_NOT_FOUND,
    ERR_ARTICLE_SLUG_EXISTS,
    ERR_CATEGORY_NOT_FOUND,
    ERR_WIKI_ACTIVE_REVISION_EXISTS,
    ERR_WIKI_GUIDES_EDITOR_ONLY,
    ERR_WIKI_REVIEW_ALREADY_EXISTS,
    ERR_WIKI_REVISION_NOT_EDITABLE,
    ERR_WIKI_REVISION_NOT_FOUND,
    ERR_WIKI_REVISION_NOT_SUBMITTED,
    ERR_WIKI_SELF_REVIEW_FORBIDDEN,
    raise_error,
)
from app.models.user import User, UserRole
from app.models.wiki_article import (
    WikiArticle,
    WikiArticleProvenance,
    WikiArticleStatus,
)
from app.models.wiki_category import WikiCategory
from app.models.wiki_revision import (
    WikiRevision,
    WikiRevisionAuthorship,
    WikiRevisionReview,
    WikiRevisionStatus,
)
from app.models.wiki_space import WikiSpace
from app.services.slug_service import generate_unique_slug

ACTIVE_AUTHOR_STATUSES = (
    WikiRevisionStatus.DRAFT,
    WikiRevisionStatus.PENDING_REVIEW,
)


def is_wiki_editor(user: User) -> bool:
    """Moderators and administrators can make publication decisions."""

    return user.role in {UserRole.MODERATOR, UserRole.ADMIN}


async def get_article_or_404(
    db: AsyncSession,
    article_id: int,
    *,
    for_update: bool = False,
) -> WikiArticle:
    statement = select(WikiArticle).where(WikiArticle.id == article_id)
    if for_update:
        statement = statement.with_for_update()
    article = (await db.execute(statement)).scalar_one_or_none()
    if article is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ARTICLE_NOT_FOUND)
    return article


async def get_revision_or_404(
    db: AsyncSession,
    revision_id: int,
    *,
    for_update: bool = False,
) -> WikiRevision:
    statement = select(WikiRevision).where(WikiRevision.id == revision_id)
    if for_update:
        statement = statement.with_for_update()
    revision = (await db.execute(statement)).scalar_one_or_none()
    if revision is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_REVISION_NOT_FOUND)
    return revision


async def load_revision(db: AsyncSession, revision_id: int) -> WikiRevision:
    """Load a revision and everything needed to serialize it without N+1 queries."""

    result = await db.execute(
        select(WikiRevision)
        .where(WikiRevision.id == revision_id)
        .options(
            selectinload(WikiRevision.article).selectinload(WikiArticle.space),
            selectinload(WikiRevision.base_revision),
            selectinload(WikiRevision.created_by),
            selectinload(WikiRevision.reviewed_by),
            selectinload(WikiRevision.peer_reviews).selectinload(
                WikiRevisionReview.reviewer
            ),
        )
        .execution_options(populate_existing=True)
    )
    revision = result.scalar_one_or_none()
    if revision is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_REVISION_NOT_FOUND)
    return revision


async def _get_space(db: AsyncSession, key: str) -> WikiSpace:
    space = (
        await db.execute(select(WikiSpace).where(WikiSpace.key == key))
    ).scalar_one_or_none()
    if space is None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_ACCESS_DENIED)
    return space


async def _ensure_category(db: AsyncSession, category_id: int) -> None:
    exists = (
        await db.execute(select(WikiCategory.id).where(WikiCategory.id == category_id))
    ).scalar_one_or_none()
    if exists is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CATEGORY_NOT_FOUND)


async def _ensure_slug_available(
    db: AsyncSession,
    slug: str,
    *,
    exclude_id: int | None = None,
) -> None:
    statement = select(WikiArticle.id).where(WikiArticle.slug == slug)
    if exclude_id is not None:
        statement = statement.where(WikiArticle.id != exclude_id)
    if (await db.execute(statement)).scalar_one_or_none() is not None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_ARTICLE_SLUG_EXISTS)


async def _next_revision_number(db: AsyncSession, article_id: int) -> int:
    result = await db.execute(
        select(func.max(WikiRevision.revision_number)).where(
            WikiRevision.article_id == article_id
        )
    )
    return int(result.scalar_one_or_none() or 0) + 1


async def _ensure_no_active_author_revision(
    db: AsyncSession,
    *,
    article_id: int,
    author_id: int,
) -> None:
    existing = (
        await db.execute(
            select(WikiRevision.id).where(
                WikiRevision.article_id == article_id,
                WikiRevision.created_by_id == author_id,
                WikiRevision.status.in_(ACTIVE_AUTHOR_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_ACTIVE_REVISION_EXISTS)


def _publish_revision_snapshot(
    article: WikiArticle,
    revision: WikiRevision,
    *,
    reviewer_id: int | None,
    review_note: str | None,
    now: datetime,
) -> None:
    revision.status = WikiRevisionStatus.PUBLISHED
    revision.reviewed_by_id = reviewer_id
    revision.review_note = review_note
    revision.reviewed_at = now
    revision.published_at = now

    article.title = revision.title
    article.summary = revision.summary
    article.content = revision.content
    article.tags = revision.tags
    article.status = WikiArticleStatus.PUBLISHED
    article.published = True
    article.published_revision_id = revision.id
    article.updated_by_id = reviewer_id or revision.created_by_id
    article.reviewed_by_id = reviewer_id
    article.reviewed_at = now
    article.rejection_reason = None


async def create_article_with_revision(
    db: AsyncSession,
    *,
    user: User,
    category_id: int,
    space_key: str,
    language: str,
    title: str,
    slug: str | None,
    summary: str,
    content: str,
    tags: list[str] | None,
    edit_summary: str | None,
    publish: bool,
    display_author: str | None = None,
    order: int = 0,
) -> WikiRevision:
    """Create an article and its first immutable/draft snapshot."""

    editor = is_wiki_editor(user)
    space = await _get_space(db, space_key)
    await _ensure_category(db, category_id)

    if not space.allows_community_authors and not editor:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_WIKI_GUIDES_EDITOR_ONLY)
    if publish and not editor:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)

    if slug is None:
        slug = await generate_unique_slug(
            db=db,
            model=WikiArticle,
            source=title,
            fallback="wiki-article",
        )
    else:
        await _ensure_slug_available(db, slug)

    provenance = (
        WikiArticleProvenance.EDITORIAL.value
        if editor
        else WikiArticleProvenance.COMMUNITY.value
    )
    article = WikiArticle(
        category_id=category_id,
        space_id=space.id,
        language=language,
        provenance=provenance,
        title=title,
        slug=slug,
        summary=summary,
        content=content,
        tags=tags,
        author=display_author or user.username,
        order=order,
        status=WikiArticleStatus.DRAFT,
        published=False,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(article)
    await db.flush()

    revision = WikiRevision(
        article_id=article.id,
        revision_number=1,
        created_by_id=user.id,
        status=WikiRevisionStatus.DRAFT,
        authorship=(
            WikiRevisionAuthorship.EDITORIAL
            if editor
            else WikiRevisionAuthorship.COMMUNITY
        ),
        title=title,
        summary=summary,
        content=content,
        tags=tags,
        edit_summary=edit_summary,
    )
    db.add(revision)
    await db.flush()

    if publish:
        now = datetime.now(timezone.utc)
        _publish_revision_snapshot(
            article,
            revision,
            reviewer_id=user.id,
            review_note=None,
            now=now,
        )
        await db.flush()

    return await load_revision(db, revision.id)


async def create_revision(
    db: AsyncSession,
    *,
    article_id: int,
    user: User,
    changes: dict[str, Any],
) -> WikiRevision:
    """Start one owned revision from the public snapshot without changing it."""

    article = await get_article_or_404(db, article_id, for_update=True)
    if (
        not article.published
        and article.created_by_id != user.id
        and not is_wiki_editor(user)
    ):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_ARTICLE_NOT_FOUND)
    await _ensure_no_active_author_revision(
        db, article_id=article.id, author_id=user.id
    )

    base = None
    if article.published_revision_id is not None:
        base = await get_revision_or_404(db, article.published_revision_id)

    source_title = base.title if base is not None else article.title
    source_summary = base.summary if base is not None else article.summary
    source_content = base.content if base is not None else article.content
    source_tags = base.tags if base is not None else article.tags

    revision = WikiRevision(
        article_id=article.id,
        revision_number=await _next_revision_number(db, article.id),
        base_revision_id=base.id if base is not None else None,
        created_by_id=user.id,
        status=WikiRevisionStatus.DRAFT,
        authorship=(
            WikiRevisionAuthorship.EDITORIAL
            if is_wiki_editor(user)
            else WikiRevisionAuthorship.COMMUNITY
        ),
        title=changes.get("title", source_title),
        summary=changes.get("summary", source_summary),
        content=changes.get("content", source_content),
        tags=changes["tags"] if "tags" in changes else source_tags,
        edit_summary=changes.get("edit_summary"),
    )
    db.add(revision)
    await db.flush()
    return await load_revision(db, revision.id)


async def update_owned_draft(
    db: AsyncSession,
    *,
    revision_id: int,
    user: User,
    changes: dict[str, Any],
) -> WikiRevision:
    revision = await get_revision_or_404(db, revision_id, for_update=True)
    if revision.created_by_id != user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    if revision.status != WikiRevisionStatus.DRAFT:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_EDITABLE)

    for field in ("title", "summary", "content", "tags", "edit_summary"):
        if field in changes:
            setattr(revision, field, changes[field])
    await db.flush()
    return await load_revision(db, revision.id)


async def submit_owned_draft(
    db: AsyncSession,
    *,
    revision_id: int,
    user: User,
    edit_summary: str | None = None,
) -> WikiRevision:
    revision = await get_revision_or_404(db, revision_id, for_update=True)
    if revision.created_by_id != user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    if revision.status != WikiRevisionStatus.DRAFT:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_EDITABLE)

    if edit_summary is not None:
        revision.edit_summary = edit_summary
    revision.status = WikiRevisionStatus.PENDING_REVIEW
    revision.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return await load_revision(db, revision.id)


async def withdraw_owned_revision(
    db: AsyncSession,
    *,
    revision_id: int,
    user: User,
) -> WikiRevision:
    revision = await get_revision_or_404(db, revision_id, for_update=True)
    if revision.created_by_id != user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    if revision.status != WikiRevisionStatus.PENDING_REVIEW:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_SUBMITTED)

    revision.status = WikiRevisionStatus.WITHDRAWN
    await db.flush()
    return await load_revision(db, revision.id)


async def retry_rejected_revision(
    db: AsyncSession,
    *,
    revision_id: int,
    user: User,
) -> WikiRevision:
    """Create a new editable draft from an immutable rejected revision."""

    rejected = await get_revision_or_404(db, revision_id, for_update=True)
    if rejected.created_by_id != user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)
    if rejected.status != WikiRevisionStatus.REJECTED:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_EDITABLE)
    await _ensure_no_active_author_revision(
        db,
        article_id=rejected.article_id,
        author_id=user.id,
    )
    article = await get_article_or_404(db, rejected.article_id, for_update=True)
    revision = WikiRevision(
        article_id=article.id,
        revision_number=await _next_revision_number(db, article.id),
        base_revision_id=article.published_revision_id,
        created_by_id=user.id,
        status=WikiRevisionStatus.DRAFT,
        authorship=rejected.authorship,
        title=rejected.title,
        summary=rejected.summary,
        content=rejected.content,
        tags=rejected.tags,
        edit_summary=rejected.edit_summary,
    )
    db.add(revision)
    await db.flush()
    return await load_revision(db, revision.id)


async def add_peer_review(
    db: AsyncSession,
    *,
    revision_id: int,
    user: User,
    verdict: Any,
    comment: str | None,
    evidence_url: str | None,
) -> WikiRevision:
    revision = await get_revision_or_404(db, revision_id, for_update=True)
    if revision.status != WikiRevisionStatus.PENDING_REVIEW:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_SUBMITTED)
    if revision.created_by_id == user.id:
        raise_error(status.HTTP_403_FORBIDDEN, ERR_WIKI_SELF_REVIEW_FORBIDDEN)

    existing = (
        await db.execute(
            select(WikiRevisionReview.id).where(
                WikiRevisionReview.revision_id == revision.id,
                WikiRevisionReview.reviewer_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVIEW_ALREADY_EXISTS)

    db.add(
        WikiRevisionReview(
            revision_id=revision.id,
            reviewer_id=user.id,
            verdict=verdict,
            comment=comment,
            evidence_url=evidence_url,
        )
    )
    await db.flush()
    return await load_revision(db, revision.id)


async def moderate_revision(
    db: AsyncSession,
    *,
    revision_id: int,
    editor: User,
    decision: str,
    review_note: str | None,
) -> WikiRevision:
    if not is_wiki_editor(editor):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)

    revision = await get_revision_or_404(db, revision_id, for_update=True)
    article = await get_article_or_404(db, revision.article_id, for_update=True)
    if revision.status != WikiRevisionStatus.PENDING_REVIEW:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_REVISION_NOT_SUBMITTED)
    if (
        revision.authorship == WikiRevisionAuthorship.COMMUNITY
        and revision.created_by_id == editor.id
    ):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_WIKI_SELF_REVIEW_FORBIDDEN)

    now = datetime.now(timezone.utc)
    revision.reviewed_by_id = editor.id
    revision.review_note = review_note
    revision.reviewed_at = now
    article.reviewed_by_id = editor.id
    article.reviewed_at = now

    if decision == "publish":
        _publish_revision_snapshot(
            article,
            revision,
            reviewer_id=editor.id,
            review_note=review_note,
            now=now,
        )
    else:
        revision.status = WikiRevisionStatus.REJECTED
        article.rejection_reason = review_note
        if article.published_revision_id is None:
            article.status = WikiArticleStatus.REJECTED
            article.published = False

    await db.flush()
    return await load_revision(db, revision.id)


async def publish_editorial_snapshot(
    db: AsyncSession,
    *,
    article: WikiArticle,
    actor_id: int | None,
    title: str,
    summary: str,
    content: str,
    tags: list[str] | None,
    publish: bool,
    edit_summary: str | None = None,
) -> WikiRevision:
    """Version a trusted admin/sync snapshot instead of mutating content invisibly."""

    await db.refresh(article, attribute_names=["id"])
    revision = WikiRevision(
        article_id=article.id,
        revision_number=await _next_revision_number(db, article.id),
        base_revision_id=article.published_revision_id,
        created_by_id=actor_id,
        status=WikiRevisionStatus.DRAFT,
        authorship=WikiRevisionAuthorship.EDITORIAL,
        title=title,
        summary=summary,
        content=content,
        tags=tags,
        edit_summary=edit_summary,
    )
    db.add(revision)
    await db.flush()
    article.title = title
    article.summary = summary
    article.content = content
    article.tags = tags
    if publish:
        _publish_revision_snapshot(
            article,
            revision,
            reviewer_id=actor_id,
            review_note=None,
            now=datetime.now(timezone.utc),
        )
    else:
        article.status = WikiArticleStatus.DRAFT
        article.published = False
        article.updated_by_id = actor_id
    await db.flush()
    return revision
