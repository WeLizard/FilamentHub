"""Feedback endpoints."""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    get_current_active_user,
    get_current_active_user_optional,
    get_current_admin_user,
)
from app.core.errors import (
    ERR_AUTH_REQUIRED,
    ERR_FEEDBACK_NOT_FOUND,
    ERR_FEEDBACK_THREAD_CLOSED,
    ERR_FILE_EXT_NOT_ALLOWED,
    ERR_FILE_SAVE_FAILED,
    ERR_FILE_SIZE_EXCEEDED,
    ERR_INVALID_FEEDBACK_STATUS,
    ERR_INVALID_FEEDBACK_TYPE,
    ERR_MAX_FILES_EXCEEDED,
    raise_error,
)
from app.core.field_encryption import decrypt_field, encrypt_field
from app.core.utils import like_pattern
from app.db.session import get_db
from app.models.feedback import (
    Feedback,
    FeedbackMessage,
    FeedbackMessageAttachment,
    FeedbackStatus,
    FeedbackType,
)
from app.models.user import User, UserRole
from app.schemas.feedback import (
    FeedbackAttachmentResponse,
    FeedbackCreate,
    FeedbackDetailResponse,
    FeedbackListResponse,
    FeedbackMarkRead,
    FeedbackMessageCreate,
    FeedbackResponse,
    FeedbackUpdate,
)
from app.services.feedback_media import (
    feedback_media_path,
    feedback_media_storage_paths,
    remove_feedback_media,
)
from app.services.file_service import WIKI_IMAGE_ALLOWED_EXTENSIONS, normalize_wiki_image_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

FEEDBACK_MAX_IMAGES = 4
FEEDBACK_MAX_IMAGE_BYTES = 8 * 1024 * 1024
FEEDBACK_MESSAGE_MAX_LENGTH = 10_000
_PUBLIC_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_CLOSED_STATUSES = (FeedbackStatus.RESOLVED, FeedbackStatus.CLOSED)

_latest_author_type = (
    select(FeedbackMessage.author_type)
    .where(FeedbackMessage.feedback_id == Feedback.id)
    .order_by(FeedbackMessage.created_at.desc(), FeedbackMessage.id.desc())
    .limit(1)
    .correlate(Feedback)
    .scalar_subquery()
)
_awaiting_reply_condition = and_(
    _latest_author_type == "user", Feedback.status.notin_(_CLOSED_STATUSES)
)


async def _load_feedback_thread(
    db: AsyncSession,
    feedback_id: int,
    *,
    for_update: bool = False,
) -> Feedback:
    statement = (
        select(Feedback)
        .options(
            selectinload(Feedback.messages).selectinload(FeedbackMessage.attachments),
            selectinload(Feedback.user),
        )
        .where(Feedback.id == feedback_id)
    )
    if for_update:
        # Lock the thread before loading messages so replies and read acknowledgements
        # use the same committed counter and message suffix.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    result = await db.execute(statement)
    feedback = result.scalar_one_or_none()
    if not feedback:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    return feedback


def _can_read_feedback(feedback: Feedback, user: User) -> bool:
    return user.role == UserRole.ADMIN or feedback.user_id == user.id


def _attachment_url(feedback_id: int, public_id: str) -> str:
    return f"/api/v1/feedback/{feedback_id}/attachments/{public_id}.webp"


def _latest_message_is_from_user(feedback: Feedback) -> bool:
    if feedback.status in _CLOSED_STATUSES or not feedback.messages:
        return False
    return feedback.messages[-1].author_type == "user"


def _feedback_extra(feedback: Feedback, awaiting_reply: bool) -> dict:
    user = feedback.user
    return {
        "user_username": user.username if user is not None else None,
        "user_language": user.legal_acceptance_language if user is not None else None,
        "awaiting_reply": awaiting_reply,
    }


def _feedback_response(feedback: Feedback, awaiting_reply: bool = False) -> FeedbackResponse:
    response = FeedbackResponse.model_validate(feedback)
    return response.model_copy(update=_feedback_extra(feedback, awaiting_reply))


def _feedback_detail_response(feedback: Feedback) -> FeedbackDetailResponse:
    response = FeedbackDetailResponse.model_validate(feedback)
    messages = [
        message.model_copy(
            update={
                "attachments": [
                    FeedbackAttachmentResponse(
                        public_id=attachment.public_id,
                        url=_attachment_url(feedback.id, attachment.public_id),
                        width=attachment.width,
                        height=attachment.height,
                    )
                    for attachment in orm_message.attachments
                ]
            }
        )
        for message, orm_message in zip(response.messages, feedback.messages, strict=True)
    ]
    return response.model_copy(
        update={
            **_feedback_extra(feedback, _latest_message_is_from_user(feedback)),
            "messages": messages,
        }
    )


@router.post("/", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_feedback(
    feedback_data: FeedbackCreate,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackResponse:
    """
    Создать обратную связь.

    Требуется авторизация. Email не нужен, так как берется из профиля пользователя.
    """
    # Получаем текущего пользователя (для обратной связи требуется авторизация)
    current_user = await get_current_active_user_optional(request, db)

    if not current_user:
        raise_error(status.HTTP_401_UNAUTHORIZED, ERR_AUTH_REQUIRED)

    # Валидация типа
    try:
        feedback_type = FeedbackType(feedback_data.type)
    except ValueError:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FEEDBACK_TYPE)

    feedback = Feedback(
        user_id=current_user.id,
        type=feedback_type,
        subject=feedback_data.subject,
        message=feedback_data.message,
        email=None,  # Email не нужен для авторизованных пользователей
        status=FeedbackStatus.OPEN,
        admin_unread_count=1,
        # Source context
        source=feedback_data.source,
        source_url=feedback_data.source_url,
        source_id=feedback_data.source_id,
    )
    if feedback_data.plugin_log:
        feedback.plugin_log = encrypt_field(feedback_data.plugin_log)
        feedback.plugin_log_size = len(feedback_data.plugin_log.encode("utf-8"))

    db.add(feedback)
    await db.flush()
    db.add(
        FeedbackMessage(
            feedback_id=feedback.id,
            author_user_id=current_user.id,
            author_type="user",
            message=feedback_data.message,
        )
    )
    await db.commit()
    await db.refresh(feedback)

    return FeedbackResponse.model_validate(feedback).model_copy(
        update={"user_username": current_user.username}
    )


@router.get("/", response_model=FeedbackListResponse)
async def list_feedback(
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status_filter: FeedbackStatus | None = Query(
        None, alias="status", description="Фильтр по статусу"
    ),
    type_filter: FeedbackType | None = Query(None, alias="type", description="Фильтр по типу"),
    source_filter: str | None = Query(
        None, alias="source", description="Фильтр по источнику (wiki_article, preset, general)"
    ),
    search: str | None = Query(None, max_length=200),
    awaiting_reply: bool = Query(False),
    sort: Literal["updated", "attention"] = Query("updated"),
) -> FeedbackListResponse:
    """Получить список обратной связи (только для админов)."""
    awaiting_flag = case((_awaiting_reply_condition, True), else_=False)
    query = (
        select(Feedback, awaiting_flag.label("awaiting_reply"))
        .outerjoin(User, Feedback.user_id == User.id)
        .options(selectinload(Feedback.user))
    )
    count_query = select(func.count(Feedback.id)).outerjoin(User, Feedback.user_id == User.id)

    filters = []
    if status_filter:
        filters.append(Feedback.status == status_filter)
    if type_filter:
        filters.append(Feedback.type == type_filter)
    if source_filter:
        filters.append(Feedback.source == source_filter)
    if awaiting_reply:
        filters.append(_awaiting_reply_condition)

    term = (search or "").strip()
    if term:
        pattern = like_pattern(term)
        conditions = [
            Feedback.subject.ilike(pattern, escape="\\"),
            Feedback.message.ilike(pattern, escape="\\"),
            Feedback.email.ilike(pattern, escape="\\"),
            User.username.ilike(pattern, escape="\\"),
        ]
        if re.fullmatch(r"#?\d+", term):
            conditions.append(Feedback.id == int(term.lstrip("#")))
        filters.append(or_(*conditions))

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = (await db.execute(count_query)).scalar() or 0

    pages = (total + size - 1) // size if total > 0 else 0
    offset = (page - 1) * size
    if sort == "attention":
        ordering = [
            case((_awaiting_reply_condition, 0), else_=1),
            case((Feedback.admin_unread_count > 0, 0), else_=1),
            Feedback.updated_at.desc(),
            Feedback.id.desc(),
        ]
    else:
        ordering = [Feedback.updated_at.desc(), Feedback.id.desc()]
    query = query.order_by(*ordering).offset(offset).limit(size)

    rows = (await db.execute(query)).all()

    return FeedbackListResponse(
        items=[_feedback_response(row[0], bool(row[1])) for row in rows],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{feedback_id}", response_model=FeedbackDetailResponse)
async def get_feedback(
    feedback_id: int,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackDetailResponse:
    """Get a feedback conversation for its owner or an administrator."""
    feedback = await _load_feedback_thread(db, feedback_id)
    if not _can_read_feedback(feedback, current_user):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    return _feedback_detail_response(feedback)


@router.get("/{feedback_id}/plugin-log")
async def download_feedback_plugin_log(
    feedback_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Return the attached plugin log as a download-only plain-text file."""
    del admin
    result = await db.execute(select(Feedback.plugin_log).where(Feedback.id == feedback_id))
    stored = result.scalar_one_or_none()
    if not stored:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    return Response(
        content=decrypt_field(stored).encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="feedback-{feedback_id}-plugin.log"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{feedback_id}/read", response_model=FeedbackDetailResponse)
async def mark_feedback_read(
    feedback_id: int,
    payload: FeedbackMarkRead,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackDetailResponse:
    """Clear only user messages already shown to the shared admin inbox."""
    del admin
    feedback = await _load_feedback_thread(db, feedback_id, for_update=True)
    latest_visible_user_message = max(
        (
            message.id
            for message in feedback.messages
            if message.author_type == "user" and message.id <= payload.through_message_id
        ),
        default=None,
    )
    if latest_visible_user_message is None:
        raise_error(status.HTTP_400_BAD_REQUEST, ERR_FEEDBACK_NOT_FOUND)

    remaining_user_messages = sum(
        1
        for message in feedback.messages
        if message.author_type == "user" and message.id > latest_visible_user_message
    )
    # Unread messages form a suffix. An older admin snapshot cannot move the
    # shared read boundary backwards, including after a new user reply.
    feedback.admin_unread_count = min(feedback.admin_unread_count, remaining_user_messages)
    await db.commit()
    feedback = await _load_feedback_thread(db, feedback.id)
    return _feedback_detail_response(feedback)


async def _find_admin_reply(
    db: AsyncSession, feedback_id: int, admin_id: int, reply_key: str | None
) -> FeedbackMessage | None:
    if not reply_key:
        return None
    result = await db.execute(
        select(FeedbackMessage).where(
            FeedbackMessage.feedback_id == feedback_id,
            FeedbackMessage.author_user_id == admin_id,
            FeedbackMessage.idempotency_key == reply_key,
        )
    )
    return result.scalar_one_or_none()


async def _apply_admin_reply(
    db: AsyncSession,
    feedback: Feedback,
    admin: User,
    response_text: str,
    reply_key: str | None,
    attachments: list[FeedbackMessageAttachment] | None = None,
) -> FeedbackMessage | None:
    """Append an admin reply and notify the author; None when it was a retry or empty."""
    if await _find_admin_reply(db, feedback.id, admin.id, reply_key):
        return None
    if not response_text and not attachments:
        return None

    responded_at = datetime.now(timezone.utc)
    feedback.admin_response = response_text or feedback.admin_response
    feedback.responded_by = admin.id
    feedback.admin_response_at = responded_at
    message = FeedbackMessage(
        author_user_id=admin.id,
        author_type="admin",
        message=response_text,
        idempotency_key=reply_key,
        created_at=responded_at,
    )
    if attachments:
        message.attachments = attachments
    feedback.messages.append(message)

    if feedback.user_id:
        from app.models.notification import NotificationType
        from app.services.notification_service import create_notification

        await create_notification(
            user_id=feedback.user_id,
            notification_type=NotificationType.ADMIN_MESSAGE,
            title="feedback_response",
            message=response_text or "feedback_response_images",
            db=db,
            link=f"/feedback/{feedback.id}",
            extra_data={
                "feedback_id": feedback.id,
                "feedback_type": feedback.type.value,
                "feedback_subject": feedback.subject,
            },
        )
    return message


def _unlink_quietly(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove feedback attachment %s", path.name, exc_info=True)


def _reply_validation_error(field: str, message: str) -> RequestValidationError:
    return RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": message, "input": None}]
    )


@router.patch("/{feedback_id}", response_model=FeedbackDetailResponse)
async def update_feedback(
    feedback_id: int,
    update_data: FeedbackUpdate,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackDetailResponse:
    """Обновить обратную связь (ответить, изменить статус) - только для админов."""
    feedback = await _load_feedback_thread(db, feedback_id, for_update=True)

    if update_data.status:
        try:
            feedback.status = FeedbackStatus(update_data.status)
        except ValueError:
            raise_error(status.HTTP_400_BAD_REQUEST, ERR_INVALID_FEEDBACK_STATUS)

    if update_data.admin_response is not None:
        await _apply_admin_reply(
            db,
            feedback,
            admin,
            update_data.admin_response.strip(),
            str(update_data.reply_idempotency_key) if update_data.reply_idempotency_key else None,
        )

    await db.commit()
    feedback = await _load_feedback_thread(db, feedback.id)

    return _feedback_detail_response(feedback)


@router.post("/{feedback_id}/admin-reply", response_model=FeedbackDetailResponse)
async def admin_reply_with_images(
    feedback_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[UUID, Form()],
    message: Annotated[str, Form()] = "",
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> FeedbackDetailResponse:
    """Reply to a thread with text and/or up to four images (admin only)."""
    uploads = images or []
    text = message.strip()
    if len(text) > FEEDBACK_MESSAGE_MAX_LENGTH:
        raise _reply_validation_error("message", "Message is too long")
    if not text and not uploads:
        raise _reply_validation_error("message", "Message or image is required")
    if len(uploads) > FEEDBACK_MAX_IMAGES:
        raise_error(
            status.HTTP_400_BAD_REQUEST,
            ERR_MAX_FILES_EXCEEDED,
            {"max": FEEDBACK_MAX_IMAGES},
        )

    exists = await db.scalar(select(Feedback.id).where(Feedback.id == feedback_id))
    if exists is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)

    normalized: list[tuple[bytes, int, int]] = []
    for upload in uploads:
        file_ext = Path(upload.filename or "").suffix.lower()
        if file_ext not in WIKI_IMAGE_ALLOWED_EXTENSIONS:
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ERR_FILE_EXT_NOT_ALLOWED,
                {"ext": file_ext, "allowed": ", ".join(sorted(WIKI_IMAGE_ALLOWED_EXTENSIONS))},
            )
        try:
            content = await upload.read(FEEDBACK_MAX_IMAGE_BYTES + 1)
        finally:
            await upload.close()
        if len(content) > FEEDBACK_MAX_IMAGE_BYTES:
            limit_mb = f"{FEEDBACK_MAX_IMAGE_BYTES / (1024 * 1024):.0f}"
            raise_error(
                status.HTTP_400_BAD_REQUEST,
                ERR_FILE_SIZE_EXCEEDED,
                {"size_mb": f">{limit_mb}", "max_mb": limit_mb},
            )
        normalized.append(await asyncio.to_thread(normalize_wiki_image_upload, content, file_ext))

    reply_key = str(idempotency_key)
    feedback = await _load_feedback_thread(db, feedback_id, for_update=True)
    if await _find_admin_reply(db, feedback.id, admin.id, reply_key):
        return _feedback_detail_response(feedback)

    written: list[Path] = []
    attachments: list[FeedbackMessageAttachment] = []
    try:
        for data, width, height in normalized:
            public_id = uuid.uuid4().hex
            storage_path = f"feedback_media/{public_id[:2]}/{public_id}.webp"
            path = feedback_media_path(storage_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("xb") as output:
                    output.write(data)
            except OSError:
                logger.warning(
                    "Failed to store feedback attachment feedback_id=%s",
                    feedback.id,
                    exc_info=True,
                )
                raise_error(status.HTTP_500_INTERNAL_SERVER_ERROR, ERR_FILE_SAVE_FAILED)
            written.append(path)
            attachments.append(
                FeedbackMessageAttachment(
                    public_id=public_id,
                    storage_path=storage_path,
                    mime_type="image/webp",
                    width=width,
                    height=height,
                    size_bytes=len(data),
                )
            )
        await _apply_admin_reply(db, feedback, admin, text, reply_key, attachments)
        await db.commit()
    except BaseException:
        await db.rollback()
        _unlink_quietly(written)
        raise

    feedback = await _load_feedback_thread(db, feedback.id)
    return _feedback_detail_response(feedback)


@router.get("/{feedback_id}/attachments/{public_id}.webp", response_class=FileResponse)
async def read_feedback_attachment(
    feedback_id: int,
    public_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Serve an attachment to the thread owner or an administrator."""
    if not _PUBLIC_ID_RE.fullmatch(public_id):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    row = (
        await db.execute(
            select(Feedback.user_id, FeedbackMessageAttachment.storage_path)
            .join(FeedbackMessage, FeedbackMessage.feedback_id == Feedback.id)
            .join(
                FeedbackMessageAttachment,
                FeedbackMessageAttachment.message_id == FeedbackMessage.id,
            )
            .where(
                Feedback.id == feedback_id,
                FeedbackMessageAttachment.public_id == public_id,
            )
        )
    ).first()
    if row is None or not (current_user.role == UserRole.ADMIN or row[0] == current_user.id):
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    path = feedback_media_path(row[1])
    if not path.is_file():
        logger.error("Feedback attachment file missing public_id=%s", public_id)
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)
    return FileResponse(
        path,
        media_type="image/webp",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/{feedback_id}/messages", response_model=FeedbackDetailResponse)
async def add_feedback_message(
    feedback_id: int,
    message_data: FeedbackMessageCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeedbackDetailResponse:
    """Add an owner reply while the conversation remains open."""
    feedback = await _load_feedback_thread(db, feedback_id, for_update=True)
    if feedback.user_id != current_user.id:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)

    idempotency_key = str(message_data.idempotency_key)
    existing_result = await db.execute(
        select(FeedbackMessage).where(
            FeedbackMessage.feedback_id == feedback.id,
            FeedbackMessage.author_user_id == current_user.id,
            FeedbackMessage.idempotency_key == idempotency_key,
        )
    )
    if existing_result.scalar_one_or_none():
        return _feedback_detail_response(feedback)

    if feedback.status in {FeedbackStatus.RESOLVED, FeedbackStatus.CLOSED}:
        raise_error(status.HTTP_409_CONFLICT, ERR_FEEDBACK_THREAD_CLOSED)

    feedback.messages.append(
        FeedbackMessage(
            author_user_id=current_user.id,
            author_type="user",
            message=message_data.message,
            idempotency_key=idempotency_key,
        )
    )
    feedback.admin_unread_count += 1
    feedback.status = FeedbackStatus.OPEN
    feedback.updated_at = datetime.now(timezone.utc)
    await db.commit()
    feedback = await _load_feedback_thread(db, feedback.id)

    return _feedback_detail_response(feedback)


@router.delete("/{feedback_id}", status_code=status.HTTP_200_OK)
async def delete_feedback(
    feedback_id: int,
    admin: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Удалить обратную связь (только для админов)."""
    feedback = await db.get(Feedback, feedback_id)

    if not feedback:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_FEEDBACK_NOT_FOUND)

    storage_paths = await feedback_media_storage_paths(db, Feedback.id == feedback_id)

    await db.delete(feedback)
    await db.commit()

    remove_feedback_media(storage_paths)

    return {"success": True}


@router.get("/my/list", response_model=FeedbackListResponse)
async def list_my_feedback(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
) -> FeedbackListResponse:
    """Получить список своей обратной связи."""
    query = (
        select(Feedback)
        .options(selectinload(Feedback.user))
        .where(Feedback.user_id == current_user.id)
    )

    # Count total
    count_query = (
        select(func.count()).select_from(Feedback).where(Feedback.user_id == current_user.id)
    )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    pages = (total + size - 1) // size if total > 0 else 0
    offset = (page - 1) * size
    query = (
        query.order_by(Feedback.updated_at.desc(), Feedback.id.desc()).offset(offset).limit(size)
    )

    result = await db.execute(query)
    feedback_list = result.scalars().all()

    return FeedbackListResponse(
        items=[_feedback_response(feedback) for feedback in feedback_list],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
