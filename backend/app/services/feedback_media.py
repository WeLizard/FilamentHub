"""Storage of images attached to feedback replies."""

import logging
from pathlib import Path

from fastapi import status
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_INVALID_FILE_PATH, raise_error
from app.models.feedback import Feedback, FeedbackMessage, FeedbackMessageAttachment
from app.services.file_service import get_upload_root_dir

logger = logging.getLogger(__name__)


def feedback_media_path(storage_path: str) -> Path:
    root = get_upload_root_dir().resolve()
    path = (root / storage_path).resolve()
    if not path.is_relative_to(root):
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FILE_PATH)
    return path


async def feedback_media_storage_paths(
    db: AsyncSession, feedback_condition: ColumnElement[bool]
) -> list[str]:
    """Collect stored files before the rows go away through a cascade."""
    result = await db.execute(
        select(FeedbackMessageAttachment.storage_path)
        .join(FeedbackMessage, FeedbackMessage.id == FeedbackMessageAttachment.message_id)
        .join(Feedback, Feedback.id == FeedbackMessage.feedback_id)
        .where(feedback_condition)
    )
    return list(result.scalars().all())


def remove_feedback_media(storage_paths: list[str]) -> None:
    for storage_path in storage_paths:
        try:
            feedback_media_path(storage_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove feedback attachment file", exc_info=True)
