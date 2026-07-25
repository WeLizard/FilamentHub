"""Previewed, idempotent and auditable administrative in-app broadcasts."""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, Query, Request
from jwt import InvalidTokenError
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import get_current_admin_user
from app.core.errors import (
    ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID,
    ERR_NOTIFICATION_CAMPAIGN_EMPTY,
    ERR_NOTIFICATION_CAMPAIGN_EXPIRED,
    ERR_NOTIFICATION_CAMPAIGN_NOT_FOUND,
    ERR_NOTIFICATION_CAMPAIGN_STATE_INVALID,
    raise_error,
)
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.notification import Notification, NotificationType
from app.models.notification_campaign import NotificationCampaign, NotificationCampaignRecipient
from app.models.user import User
from app.schemas.notification_campaign import (
    NotificationCampaignConfirm,
    NotificationCampaignDraft,
    NotificationCampaignHistoryItem,
    NotificationCampaignHistoryResponse,
    NotificationCampaignPreviewResponse,
    NotificationCampaignRecipientPreview,
    NotificationCampaignSendResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/communications/broadcasts", tags=["admin"])

_CONFIRMATION_TYPE = "notification_campaign_confirmation"
_CONFIRMATION_MINUTES = 10
_INSERT_CHUNK_SIZE = 500


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _campaign_digest(*, data: NotificationCampaignDraft, recipient_ids: list[int]) -> str:
    payload = {
        "audience": data.audience,
        "link": data.link,
        "message": data.message,
        "recipient_ids": recipient_ids,
        "title": data.title,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _confirmation_token(*, campaign: NotificationCampaign) -> str:
    return jwt.encode(
        {
            "type": _CONFIRMATION_TYPE,
            "campaign_id": campaign.public_id,
            "admin_id": campaign.created_by_id,
            "digest": campaign.confirmation_digest,
            "exp": campaign.confirmation_expires_at,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _decode_confirmation_token(token: str, admin_id: int) -> tuple[str, str]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
            leeway=30,
        )
        if payload.get("type") != _CONFIRMATION_TYPE or payload.get("admin_id") != admin_id:
            raise ValueError("Invalid campaign confirmation identity")
        campaign_id = str(UUID(str(payload.get("campaign_id"))))
        digest = payload.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Invalid campaign confirmation digest")
    except (InvalidTokenError, TypeError, ValueError):
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID)
    return campaign_id, digest


async def _recipient_rows(
    *,
    db: AsyncSession,
    data: NotificationCampaignDraft,
) -> tuple[list[tuple[int, str, str, str | None]], list[int]]:
    query = select(User.id, User.email, User.username, User.full_name).order_by(User.id)
    excluded: list[int] = []
    if data.audience == "active":
        query = query.where(User.active.is_(True))
    elif data.audience == "selected":
        requested_ids = list(dict.fromkeys(data.user_ids))
        query = query.where(User.id.in_(requested_ids), User.active.is_(True))
    rows = [(row.id, row.email, row.username, row.full_name) for row in (await db.execute(query))]
    if data.audience == "selected":
        resolved_ids = {row[0] for row in rows}
        excluded = [user_id for user_id in data.user_ids if user_id not in resolved_ids]
    return rows, excluded


def _history_item(campaign: NotificationCampaign) -> NotificationCampaignHistoryItem:
    now = datetime.now(timezone.utc)
    status = campaign.status
    if status == "draft" and _utc(campaign.confirmation_expires_at) < now:
        status = "expired"
    creator = campaign.created_by
    return NotificationCampaignHistoryItem(
        campaign_id=campaign.public_id,
        audience=campaign.audience,
        title=campaign.title,
        message=campaign.message,
        link=campaign.link,
        recipient_count=campaign.recipient_count,
        status=status,
        created_by_id=campaign.created_by_id,
        created_by_name=creator.full_name or creator.username,
        created_at=campaign.created_at,
        confirmation_expires_at=campaign.confirmation_expires_at,
        sent_at=campaign.sent_at,
    )


@router.post("/preview", response_model=NotificationCampaignPreviewResponse, status_code=201)
@limiter.limit("30/hour")
async def preview_notification_campaign(
    request: Request,
    data: NotificationCampaignDraft,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> NotificationCampaignPreviewResponse:
    """Persist an exact recipient snapshot without delivering notifications."""
    rows, excluded_user_ids = await _recipient_rows(db=db, data=data)
    if not rows:
        raise_error(400, ERR_NOTIFICATION_CAMPAIGN_EMPTY)

    recipient_ids = [row[0] for row in rows]
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CONFIRMATION_MINUTES)
    campaign = NotificationCampaign(
        public_id=str(uuid4()),
        audience=data.audience,
        title=data.title,
        message=data.message,
        link=data.link,
        recipient_count=len(recipient_ids),
        status="draft",
        confirmation_digest=_campaign_digest(data=data, recipient_ids=recipient_ids),
        confirmation_expires_at=expires_at,
        created_by_id=admin.id,
    )
    db.add(campaign)
    await db.flush()
    for start in range(0, len(recipient_ids), _INSERT_CHUNK_SIZE):
        await db.execute(
            insert(NotificationCampaignRecipient),
            [
                {"campaign_id": campaign.id, "user_id": user_id}
                for user_id in recipient_ids[start : start + _INSERT_CHUNK_SIZE]
            ],
        )
    await db.commit()

    return NotificationCampaignPreviewResponse(
        campaign_id=campaign.public_id,
        audience=data.audience,
        recipient_count=len(recipient_ids),
        recipient_sample=[
            NotificationCampaignRecipientPreview(
                id=user_id,
                email=email,
                username=username,
                full_name=full_name,
            )
            for user_id, email, username, full_name in rows[:5]
        ],
        excluded_user_ids=excluded_user_ids,
        title=data.title,
        message=data.message,
        link=data.link,
        confirmation_token=_confirmation_token(campaign=campaign),
        confirmation_expires_at=expires_at,
    )


@router.post("/confirm", response_model=NotificationCampaignSendResponse)
@limiter.limit("10/hour")
async def confirm_notification_campaign(
    request: Request,
    data: NotificationCampaignConfirm,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> NotificationCampaignSendResponse:
    """Deliver one previously previewed recipient snapshot exactly once."""
    public_id, token_digest = _decode_confirmation_token(data.confirmation_token, admin.id)
    campaign = await db.scalar(
        select(NotificationCampaign)
        .where(NotificationCampaign.public_id == public_id)
        .with_for_update()
    )
    if campaign is None or campaign.created_by_id != admin.id:
        raise_error(404, ERR_NOTIFICATION_CAMPAIGN_NOT_FOUND)
    if not hmac.compare_digest(campaign.confirmation_digest, token_digest):
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID)
    if campaign.status == "sent" and campaign.sent_at is not None:
        return NotificationCampaignSendResponse(
            campaign_id=campaign.public_id,
            status="sent",
            recipient_count=campaign.recipient_count,
            replayed=True,
            sent_at=campaign.sent_at,
        )
    if campaign.status != "draft":
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_STATE_INVALID)
    if _utc(campaign.confirmation_expires_at) < datetime.now(timezone.utc):
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_EXPIRED)

    recipient_ids = list(
        (
            await db.scalars(
                select(NotificationCampaignRecipient.user_id)
                .where(NotificationCampaignRecipient.campaign_id == campaign.id)
                .order_by(NotificationCampaignRecipient.id)
            )
        ).all()
    )
    if len(recipient_ids) != campaign.recipient_count or not recipient_ids:
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID)
    digest_source = NotificationCampaignDraft(
        audience=campaign.audience,
        user_ids=recipient_ids if campaign.audience == "selected" else [],
        title=campaign.title,
        message=campaign.message,
        link=campaign.link,
    )
    snapshot_digest = _campaign_digest(data=digest_source, recipient_ids=recipient_ids)
    if not hmac.compare_digest(campaign.confirmation_digest, snapshot_digest):
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_CONFIRMATION_INVALID)

    notification_rows = [
        {
            "user_id": user_id,
            "campaign_id": campaign.id,
            "type": NotificationType.ADMIN_MESSAGE,
            "title": campaign.title,
            "message": campaign.message,
            "link": campaign.link,
            "extra_data": {"campaign_id": campaign.public_id},
            "read": False,
        }
        for user_id in recipient_ids
    ]
    try:
        for start in range(0, len(notification_rows), _INSERT_CHUNK_SIZE):
            await db.execute(
                insert(Notification),
                notification_rows[start : start + _INSERT_CHUNK_SIZE],
            )
        sent_at = datetime.now(timezone.utc)
        campaign.status = "sent"
        campaign.sent_at = sent_at
        await db.commit()
    except IntegrityError:
        await db.rollback()
        replayed_campaign = await db.scalar(
            select(NotificationCampaign).where(NotificationCampaign.public_id == public_id)
        )
        if replayed_campaign is None or replayed_campaign.sent_at is None:
            raise
        return NotificationCampaignSendResponse(
            campaign_id=replayed_campaign.public_id,
            status="sent",
            recipient_count=replayed_campaign.recipient_count,
            replayed=True,
            sent_at=replayed_campaign.sent_at,
        )

    logger.info(
        "Admin %s sent notification campaign %s to %s users",
        admin.id,
        campaign.public_id,
        campaign.recipient_count,
    )
    return NotificationCampaignSendResponse(
        campaign_id=campaign.public_id,
        status="sent",
        recipient_count=campaign.recipient_count,
        replayed=False,
        sent_at=sent_at,
    )


@router.delete("/{campaign_id}")
@limiter.limit("30/hour")
async def cancel_notification_campaign(
    request: Request,
    campaign_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, bool]:
    """Cancel an unsent preview; delivered campaigns are immutable."""
    campaign = await db.scalar(
        select(NotificationCampaign).where(NotificationCampaign.public_id == campaign_id)
    )
    if campaign is None or campaign.created_by_id != admin.id:
        raise_error(404, ERR_NOTIFICATION_CAMPAIGN_NOT_FOUND)
    if campaign.status != "draft":
        raise_error(409, ERR_NOTIFICATION_CAMPAIGN_STATE_INVALID)
    campaign.status = "cancelled"
    await db.commit()
    return {"cancelled": True}


@router.get("", response_model=NotificationCampaignHistoryResponse)
async def list_notification_campaigns(
    db: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
) -> NotificationCampaignHistoryResponse:
    """List campaign history for administrative audit and operational visibility."""
    del admin
    total = int(await db.scalar(select(func.count(NotificationCampaign.id))) or 0)
    campaigns = list(
        (
            await db.scalars(
                select(NotificationCampaign)
                .options(selectinload(NotificationCampaign.created_by))
                .order_by(NotificationCampaign.created_at.desc(), NotificationCampaign.id.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
    )
    return NotificationCampaignHistoryResponse(
        items=[_history_item(campaign) for campaign in campaigns],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size) if total else 0,
    )
