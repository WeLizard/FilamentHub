"""Safe storage and publication lifecycle for user-supplied Wiki images."""

import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_ACCESS_DENIED,
    ERR_FILE_SAVE_FAILED,
    ERR_INVALID_FILE_PATH,
    ERR_WIKI_MEDIA_IN_USE,
    ERR_WIKI_MEDIA_NOT_FOUND,
    ERR_WIKI_MEDIA_QUOTA_EXCEEDED,
    raise_error,
)
from app.models.user import User, UserRole
from app.models.wiki_article import WikiArticle
from app.models.wiki_media import WikiMediaAsset
from app.models.wiki_revision import WikiRevision
from app.services.file_service import get_upload_root_dir, normalize_wiki_image_upload

logger = logging.getLogger(__name__)

WIKI_MEDIA_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
WIKI_MEDIA_MAX_USER_BYTES = 100 * 1024 * 1024
WIKI_MEDIA_MAX_USER_ASSETS = 200
WIKI_MEDIA_ROUTE_PREFIX = "/api/v1/wiki/media/"
_MEDIA_REFERENCE_RE = re.compile(
    r"/api/v1/wiki/media/(?P<public_id>[0-9a-f]{32})\.webp(?:[?#][^\s)]*)?"
)


def _is_wiki_editor(user: User) -> bool:
    return user.role in {UserRole.MODERATOR, UserRole.ADMIN}


def wiki_media_url(public_id: str) -> str:
    return f"{WIKI_MEDIA_ROUTE_PREFIX}{public_id}.webp"


def referenced_media_ids(content: str) -> set[str]:
    """Return server-managed asset identifiers referenced by Markdown."""

    return {match.group("public_id") for match in _MEDIA_REFERENCE_RE.finditer(content)}


def _storage_path(public_id: str) -> str:
    return f"wiki_media/{public_id[:2]}/{public_id}.webp"


def resolve_wiki_media_path(storage_path: str) -> Path:
    root = get_upload_root_dir().resolve()
    path = (root / storage_path).resolve()
    if not path.is_relative_to(root):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_PATH)
    return path


async def create_wiki_media_asset(
    db: AsyncSession,
    *,
    user: User,
    content: bytes,
    file_ext: str,
) -> WikiMediaAsset:
    """Normalize one upload, enforce an account quota, and persist only WebP."""

    # Serialize quota decisions per account on PostgreSQL. SQLite ignores the
    # lock, which is sufficient for deterministic single-process tests.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    count, used_bytes = (
        await db.execute(
            select(
                func.count(WikiMediaAsset.id),
                func.coalesce(func.sum(WikiMediaAsset.size_bytes), 0),
            ).where(WikiMediaAsset.uploaded_by_id == user.id)
        )
    ).one()
    if int(count) >= WIKI_MEDIA_MAX_USER_ASSETS:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_WIKI_MEDIA_QUOTA_EXCEEDED,
            {"max_assets": WIKI_MEDIA_MAX_USER_ASSETS, "max_mb": 100},
        )

    normalized, width, height = normalize_wiki_image_upload(content, file_ext)
    if int(used_bytes) + len(normalized) > WIKI_MEDIA_MAX_USER_BYTES:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_WIKI_MEDIA_QUOTA_EXCEEDED,
            {"max_assets": WIKI_MEDIA_MAX_USER_ASSETS, "max_mb": 100},
        )

    public_id = uuid.uuid4().hex
    storage_path = _storage_path(public_id)
    file_path = resolve_wiki_media_path(storage_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with file_path.open("xb") as output:
            output.write(normalized)
    except OSError:
        logger.warning(
            "Failed to store normalized Wiki media user_id=%s public_id=%s",
            user.id,
            public_id,
            exc_info=True,
        )
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_FILE_SAVE_FAILED)

    asset = WikiMediaAsset(
        public_id=public_id,
        uploaded_by_id=user.id,
        storage_path=storage_path,
        mime_type="image/webp",
        width=width,
        height=height,
        size_bytes=len(normalized),
        published=False,
    )
    db.add(asset)
    try:
        await db.flush()
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    logger.info(
        "Stored normalized Wiki media user_id=%s public_id=%s dimensions=%sx%s bytes=%s",
        user.id,
        public_id,
        width,
        height,
        len(normalized),
    )
    return asset


async def get_wiki_media_asset(
    db: AsyncSession,
    public_id: str,
) -> WikiMediaAsset:
    asset = (
        await db.execute(
            select(WikiMediaAsset).where(WikiMediaAsset.public_id == public_id)
        )
    ).scalar_one_or_none()
    if asset is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_MEDIA_NOT_FOUND)
    return asset


async def list_unpublished_user_wiki_media(
    db: AsyncSession,
    user_id: int,
) -> list[WikiMediaAsset]:
    """List the uploader's reusable private assets, newest first."""

    return list(
        (
            await db.execute(
                select(WikiMediaAsset)
                .where(
                    WikiMediaAsset.uploaded_by_id == user_id,
                    WikiMediaAsset.published.is_(False),
                )
                .order_by(WikiMediaAsset.created_at.desc(), WikiMediaAsset.id.desc())
                .limit(WIKI_MEDIA_MAX_USER_ASSETS)
            )
        ).scalars().all()
    )


async def delete_unpublished_wiki_media_asset(
    db: AsyncSession,
    *,
    public_id: str,
    user: User,
) -> None:
    """Delete an unused private upload owned by the current user."""

    asset = (
        await db.execute(
            select(WikiMediaAsset)
            .where(WikiMediaAsset.public_id == public_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        asset is None
        or asset.published
        or asset.uploaded_by_id != user.id
    ):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_WIKI_MEDIA_NOT_FOUND)

    reference = f"%{wiki_media_url(public_id)}%"
    revision_in_use = (
        await db.execute(
            select(WikiRevision.id)
            .where(WikiRevision.content.like(reference))
            .limit(1)
        )
    ).scalar_one_or_none()
    article_in_use = (
        await db.execute(
            select(WikiArticle.id)
            .where(WikiArticle.content.like(reference))
            .limit(1)
        )
    ).scalar_one_or_none()
    if revision_in_use is not None or article_in_use is not None:
        raise_error(status.HTTP_409_CONFLICT, ERR_WIKI_MEDIA_IN_USE)

    file_path = resolve_wiki_media_path(asset.storage_path)
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "Failed to delete staged Wiki media public_id=%s",
            public_id,
            exc_info=True,
        )
        raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_FILE_SAVE_FAILED)
    await db.delete(asset)


def can_view_wiki_media(asset: WikiMediaAsset, user: User | None) -> bool:
    if asset.published:
        return True
    if user is None:
        return False
    return asset.uploaded_by_id == user.id or _is_wiki_editor(user)


async def validate_wiki_media_references(
    db: AsyncSession,
    *,
    content: str,
    user: User,
) -> None:
    """Prevent drafts from embedding missing or another user's staged asset."""

    public_ids = referenced_media_ids(content)
    if not public_ids:
        return
    assets = (
        await db.execute(
            select(WikiMediaAsset).where(WikiMediaAsset.public_id.in_(public_ids))
        )
    ).scalars().all()
    if len(assets) != len(public_ids):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_WIKI_MEDIA_NOT_FOUND)
    if any(
        not asset.published
        and asset.uploaded_by_id != user.id
        for asset in assets
    ):
        raise_error(status.HTTP_403_FORBIDDEN, ERR_ACCESS_DENIED)


async def publish_referenced_wiki_media(db: AsyncSession, content: str) -> None:
    """Make only assets in an approved/published snapshot anonymously readable."""

    public_ids = referenced_media_ids(content)
    if not public_ids:
        return
    assets = (
        await db.execute(
            select(WikiMediaAsset)
            .where(WikiMediaAsset.public_id.in_(public_ids))
            .with_for_update()
        )
    ).scalars().all()
    if len(assets) != len(public_ids):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_WIKI_MEDIA_NOT_FOUND)
    now = datetime.now(timezone.utc)
    for asset in assets:
        if not asset.published:
            asset.published = True
            asset.published_at = now


async def delete_unpublished_user_wiki_media(
    db: AsyncSession,
    user_id: int,
) -> None:
    """Remove private media when its owning account is deleted."""

    assets = (
        await db.execute(
            select(WikiMediaAsset).where(
                WikiMediaAsset.uploaded_by_id == user_id,
                WikiMediaAsset.published.is_(False),
            )
        )
    ).scalars().all()
    for asset in assets:
        try:
            resolve_wiki_media_path(asset.storage_path).unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "Failed to delete unpublished Wiki media public_id=%s",
                asset.public_id,
                exc_info=True,
            )
        await db.delete(asset)
