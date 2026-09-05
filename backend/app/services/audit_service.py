"""Append bounded audit events inside the operation's existing transaction."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditAction, AuditEvent, AuditReason, AuditResult


async def record_audit_event(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor_user_id: int | None,
    target_user_id: int,
    reason: AuditReason,
    occurred_at: datetime | None = None,
    correlation_id: UUID | None = None,
) -> AuditEvent:
    """Persist with the mutation, never in a separate best-effort transaction.

    The correlation UUID identifies this operation, not a caller-supplied request.
    No unstructured metadata or credential/session identifiers are accepted.
    """
    if not isinstance(action, AuditAction) or not isinstance(reason, AuditReason):
        raise ValueError("Audit action and reason must be bounded codes")
    if correlation_id is not None and not isinstance(correlation_id, UUID):
        raise ValueError("Audit correlation must be an operation UUID")
    event = AuditEvent(
        action=action.value,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        result=AuditResult.SUCCESS.value,
        reason=reason.value,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        correlation_id=correlation_id or uuid4(),
    )
    db.add(event)
    await db.flush()
    return event
