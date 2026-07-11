"""CRM-lite endpoints: customers, versioned quotes, and production orders."""

import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.dependencies import require_calculator_access
from app.core.errors import (
    ERR_CRM_CUSTOMER_NOT_FOUND,
    ERR_CRM_INVALID_STATUS_TRANSITION,
    ERR_CRM_ORDER_NOT_FOUND,
    ERR_CRM_QUOTE_HAS_NO_DOCUMENT,
    ERR_CRM_QUOTE_LOCKED,
    ERR_CRM_QUOTE_NOT_FOUND,
    ERR_CRM_QUOTE_NUMBER_EXISTS,
    raise_error,
)
from app.db.session import get_db
from app.models.calculator_history_entry import CalculatorHistoryEntry
from app.models.calculator_profile import UserCalculatorProfile
from app.models.crm import (
    CrmCustomer,
    CrmOrder,
    CrmOrderStatus,
    CrmQuote,
    CrmQuoteEvent,
    CrmQuoteEventType,
    CrmQuoteLine,
    CrmQuoteStatus,
    CrmQuoteVersion,
)
from app.models.shared_quote import SharedQuote
from app.models.user import User
from app.schemas.crm import (
    CrmCustomerCreate,
    CrmCustomerListResponse,
    CrmCustomerResponse,
    CrmCustomerUpdate,
    CrmOrderListResponse,
    CrmOrderResponse,
    CrmOrderUpdate,
    CrmQuoteCreate,
    CrmQuoteDetailResponse,
    CrmQuoteEventResponse,
    CrmQuoteListResponse,
    CrmQuoteResponse,
    CrmQuoteStatusUpdate,
    CrmQuoteUpdate,
    CrmQuoteVersionCreate,
    CrmQuoteVersionPayload,
    CrmQuoteVersionResponse,
    CrmShareQuoteResponse,
    CrmWorkspaceSummary,
)

router = APIRouter(prefix="/crm", tags=["crm"])

MONEY_STEP = Decimal("0.01")
SHARED_QUOTE_LIFETIME_DAYS = 90

QUOTE_STATUS_TRANSITIONS: dict[CrmQuoteStatus, set[CrmQuoteStatus]] = {
    CrmQuoteStatus.DRAFT: {CrmQuoteStatus.SENT, CrmQuoteStatus.ACCEPTED, CrmQuoteStatus.REJECTED},
    CrmQuoteStatus.SENT: {CrmQuoteStatus.DRAFT, CrmQuoteStatus.ACCEPTED, CrmQuoteStatus.REJECTED, CrmQuoteStatus.EXPIRED},
    CrmQuoteStatus.ACCEPTED: set(),
    CrmQuoteStatus.REJECTED: {CrmQuoteStatus.DRAFT},
    CrmQuoteStatus.EXPIRED: {CrmQuoteStatus.DRAFT},
}

ORDER_STATUS_TRANSITIONS: dict[CrmOrderStatus, set[CrmOrderStatus]] = {
    CrmOrderStatus.NEW: {CrmOrderStatus.PLANNED, CrmOrderStatus.IN_PRODUCTION, CrmOrderStatus.CANCELLED},
    CrmOrderStatus.PLANNED: {CrmOrderStatus.NEW, CrmOrderStatus.IN_PRODUCTION, CrmOrderStatus.CANCELLED},
    CrmOrderStatus.IN_PRODUCTION: {CrmOrderStatus.PLANNED, CrmOrderStatus.READY, CrmOrderStatus.CANCELLED},
    CrmOrderStatus.READY: {CrmOrderStatus.IN_PRODUCTION, CrmOrderStatus.COMPLETED, CrmOrderStatus.CANCELLED},
    CrmOrderStatus.COMPLETED: set(),
    CrmOrderStatus.CANCELLED: {CrmOrderStatus.NEW},
}


def _money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def _customer_snapshot(customer: CrmCustomer | None) -> dict:
    if customer is None:
        return {}
    return {
        "id": customer.id,
        "name": customer.name,
        "contact_name": customer.contact_name,
        "email": customer.email,
        "phone": customer.phone,
        "inn": customer.inn,
        "address": customer.address,
    }


def _serialize_customer(customer: CrmCustomer | None) -> CrmCustomerResponse | None:
    return CrmCustomerResponse.model_validate(customer) if customer is not None else None


def _serialize_line(line: CrmQuoteLine):
    from app.schemas.crm import CrmQuoteLineResponse

    return CrmQuoteLineResponse(
        id=line.id,
        position=line.position,
        title=line.title,
        details=list(line.details or []),
        quantity=float(line.quantity),
        unit=line.unit,
        unit_price=float(line.unit_price),
        total_price=float(line.total_price),
        source_data=line.source_data,
    )


def _serialize_version(version: CrmQuoteVersion) -> CrmQuoteVersionResponse:
    return CrmQuoteVersionResponse(
        id=version.id,
        version_number=version.version_number,
        source_history_id=version.source_history_id,
        shared_quote_id=version.shared_quote_id,
        seller_snapshot=dict(version.seller_snapshot or {}),
        customer_snapshot=dict(version.customer_snapshot or {}),
        calculation_snapshot=version.calculation_snapshot,
        payment_terms=version.payment_terms,
        disclaimer_mode=version.disclaimer_mode,
        subtotal=float(version.subtotal),
        tax_total=float(version.tax_total),
        grand_total=float(version.grand_total),
        html_content=version.html_content,
        lines=[_serialize_line(line) for line in version.lines],
        created_at=version.created_at,
    )


def _serialize_order(order: CrmOrder | None) -> CrmOrderResponse | None:
    if order is None:
        return None
    return CrmOrderResponse(
        id=order.id,
        quote_id=order.quote_id,
        customer_id=order.customer_id,
        number=order.number,
        title=order.title,
        status=order.status,
        currency=order.currency,
        total=float(order.total),
        due_date=order.due_date,
        note=order.note,
        completed_at=order.completed_at,
        created_at=order.created_at,
        updated_at=order.updated_at,
        customer=_serialize_customer(order.customer),
    )


def _current_version(quote: CrmQuote) -> CrmQuoteVersion:
    if not quote.versions:
        raise RuntimeError(f"CRM quote {quote.id} has no versions")
    return quote.versions[-1]


def _serialize_quote(quote: CrmQuote) -> CrmQuoteResponse:
    return CrmQuoteResponse(
        id=quote.id,
        customer_id=quote.customer_id,
        number=quote.number,
        title=quote.title,
        status=quote.status,
        currency=quote.currency,
        valid_until=quote.valid_until,
        sent_at=quote.sent_at,
        accepted_at=quote.accepted_at,
        rejected_at=quote.rejected_at,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        customer=_serialize_customer(quote.customer),
        current_version=_serialize_version(_current_version(quote)),
        order=_serialize_order(quote.order),
    )


def _serialize_quote_detail(quote: CrmQuote) -> CrmQuoteDetailResponse:
    base = _serialize_quote(quote).model_dump()
    return CrmQuoteDetailResponse(
        **base,
        versions=[_serialize_version(version) for version in quote.versions],
        events=[CrmQuoteEventResponse.model_validate(event) for event in quote.events],
    )


def _quote_load_options():
    return (
        selectinload(CrmQuote.customer),
        selectinload(CrmQuote.versions).selectinload(CrmQuoteVersion.lines),
        selectinload(CrmQuote.events),
        selectinload(CrmQuote.order).selectinload(CrmOrder.customer),
    )


async def _load_customer(db: AsyncSession, user_id: int, customer_id: int) -> CrmCustomer:
    customer = await db.scalar(
        select(CrmCustomer).where(CrmCustomer.id == customer_id, CrmCustomer.user_id == user_id)
    )
    if customer is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CRM_CUSTOMER_NOT_FOUND)
    return customer


async def _load_quote(db: AsyncSession, user_id: int, quote_id: int) -> CrmQuote:
    quote = (
        await db.execute(
            select(CrmQuote)
            .execution_options(populate_existing=True)
            .options(*_quote_load_options())
            .where(CrmQuote.id == quote_id, CrmQuote.user_id == user_id)
        )
    ).scalar_one_or_none()
    if quote is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CRM_QUOTE_NOT_FOUND)
    return quote


async def _load_order(db: AsyncSession, user_id: int, order_id: int) -> CrmOrder:
    order = (
        await db.execute(
            select(CrmOrder)
            .execution_options(populate_existing=True)
            .options(selectinload(CrmOrder.customer))
            .where(CrmOrder.id == order_id, CrmOrder.user_id == user_id)
        )
    ).scalar_one_or_none()
    if order is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CRM_ORDER_NOT_FOUND)
    return order


async def _validate_source_history(
    db: AsyncSession, user_id: int, source_history_id: int | None
) -> None:
    if source_history_id is None:
        return
    exists = await db.scalar(
        select(CalculatorHistoryEntry.id).where(
            CalculatorHistoryEntry.id == source_history_id,
            CalculatorHistoryEntry.user_id == user_id,
        )
    )
    if exists is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_CRM_QUOTE_NOT_FOUND)


async def _add_version(
    db: AsyncSession,
    quote: CrmQuote,
    payload: CrmQuoteVersionPayload,
    version_number: int,
    actor_user_id: int,
) -> CrmQuoteVersion:
    await _validate_source_history(db, quote.user_id, payload.source_history_id)
    line_totals = [
        _money(Decimal(str(line.quantity)) * _money(line.unit_price)) for line in payload.lines
    ]
    subtotal = _money(sum(line_totals, Decimal("0")))
    tax_total = _money(payload.tax_total)
    version = CrmQuoteVersion(
        quote_id=quote.id,
        version_number=version_number,
        source_history_id=payload.source_history_id,
        seller_snapshot=payload.seller_snapshot,
        customer_snapshot=payload.customer_snapshot,
        calculation_snapshot=payload.calculation_snapshot,
        payment_terms=payload.payment_terms,
        disclaimer_mode=payload.disclaimer_mode,
        subtotal=subtotal,
        tax_total=tax_total,
        grand_total=_money(subtotal + tax_total),
        html_content=payload.html_content,
    )
    db.add(version)
    await db.flush()
    for position, (line, total) in enumerate(zip(payload.lines, line_totals, strict=True), start=1):
        db.add(
            CrmQuoteLine(
                version_id=version.id,
                position=position,
                title=line.title.strip(),
                details=[detail.strip() for detail in line.details if detail.strip()],
                quantity=Decimal(str(line.quantity)),
                unit=line.unit.strip(),
                unit_price=_money(line.unit_price),
                total_price=_money(total),
                source_data=line.source_data,
            )
        )
    db.add(
        CrmQuoteEvent(
            quote_id=quote.id,
            actor_user_id=actor_user_id,
            event_type=CrmQuoteEventType.VERSION_CREATED,
            details={"version_number": version_number},
        )
    )
    return version


@router.get("/summary", response_model=CrmWorkspaceSummary)
async def get_workspace_summary(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmWorkspaceSummary:
    """Return compact business metrics for the workspace header."""
    customer_count = await db.scalar(
        select(func.count()).select_from(CrmCustomer).where(
            CrmCustomer.user_id == current_user.id, CrmCustomer.archived.is_(False)
        )
    ) or 0
    quote_counts = dict(
        (
            await db.execute(
                select(CrmQuote.status, func.count(CrmQuote.id))
                .where(CrmQuote.user_id == current_user.id)
                .group_by(CrmQuote.status)
            )
        ).all()
    )
    order_counts = dict(
        (
            await db.execute(
                select(CrmOrder.status, func.count(CrmOrder.id))
                .where(CrmOrder.user_id == current_user.id)
                .group_by(CrmOrder.status)
            )
        ).all()
    )
    sent_quotes = (
        await db.execute(
            select(CrmQuote)
            .options(selectinload(CrmQuote.versions))
            .where(CrmQuote.user_id == current_user.id, CrmQuote.status == CrmQuoteStatus.SENT)
        )
    ).scalars().all()
    awaiting_by_currency: dict[str, Decimal] = {}
    for quote in sent_quotes:
        awaiting_by_currency[quote.currency] = (
            awaiting_by_currency.get(quote.currency, Decimal("0"))
            + Decimal(str(_current_version(quote).grand_total))
        )
    accepted_rows = (
        await db.execute(
            select(CrmOrder.currency, func.sum(CrmOrder.total))
            .where(CrmOrder.user_id == current_user.id)
            .group_by(CrmOrder.currency)
        )
    ).all()
    active_statuses = {
        CrmOrderStatus.NEW,
        CrmOrderStatus.PLANNED,
        CrmOrderStatus.IN_PRODUCTION,
        CrmOrderStatus.READY,
    }
    return CrmWorkspaceSummary(
        customers_total=customer_count,
        quotes_draft=quote_counts.get(CrmQuoteStatus.DRAFT, 0),
        quotes_sent=quote_counts.get(CrmQuoteStatus.SENT, 0),
        quotes_accepted=quote_counts.get(CrmQuoteStatus.ACCEPTED, 0),
        orders_active=sum(order_counts.get(item, 0) for item in active_statuses),
        orders_completed=order_counts.get(CrmOrderStatus.COMPLETED, 0),
        amount_awaiting_decision={currency: float(total) for currency, total in awaiting_by_currency.items()},
        accepted_amount={currency: float(total) for currency, total in accepted_rows},
    )


@router.get("/customers", response_model=CrmCustomerListResponse)
async def list_customers(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(None, max_length=255),
    include_archived: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
) -> CrmCustomerListResponse:
    filters = [CrmCustomer.user_id == current_user.id]
    if not include_archived:
        filters.append(CrmCustomer.archived.is_(False))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                CrmCustomer.name.ilike(pattern),
                CrmCustomer.contact_name.ilike(pattern),
                CrmCustomer.email.ilike(pattern),
                CrmCustomer.phone.ilike(pattern),
                CrmCustomer.inn.ilike(pattern),
            )
        )
    total = await db.scalar(select(func.count()).select_from(CrmCustomer).where(*filters)) or 0
    customers = (
        await db.execute(
            select(CrmCustomer)
            .where(*filters)
            .order_by(CrmCustomer.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().all()
    return CrmCustomerListResponse(
        items=[CrmCustomerResponse.model_validate(customer) for customer in customers], total=total
    )


@router.post("/customers", response_model=CrmCustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CrmCustomerCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmCustomerResponse:
    customer = CrmCustomer(user_id=current_user.id, **payload.model_dump(mode="json"))
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return CrmCustomerResponse.model_validate(customer)


@router.patch("/customers/{customer_id}", response_model=CrmCustomerResponse)
async def update_customer(
    customer_id: int,
    payload: CrmCustomerUpdate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmCustomerResponse:
    customer = await _load_customer(db, current_user.id, customer_id)
    for field_name, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(customer, field_name, value)
    await db.commit()
    await db.refresh(customer)
    return CrmCustomerResponse.model_validate(customer)


@router.get("/quotes", response_model=CrmQuoteListResponse)
async def list_quotes(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: CrmQuoteStatus | None = Query(None, alias="status"),
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
) -> CrmQuoteListResponse:
    filters = [CrmQuote.user_id == current_user.id]
    if status_filter is not None:
        filters.append(CrmQuote.status == status_filter)
    query = select(CrmQuote).outerjoin(CrmCustomer).where(*filters)
    count_query = select(func.count(CrmQuote.id)).outerjoin(CrmCustomer).where(*filters)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        search_filter = or_(
            CrmQuote.number.ilike(pattern),
            CrmQuote.title.ilike(pattern),
            CrmCustomer.name.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    total = await db.scalar(count_query) or 0
    quotes = (
        await db.execute(
            query.options(*_quote_load_options())
            .order_by(CrmQuote.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().unique().all()
    return CrmQuoteListResponse(items=[_serialize_quote(quote) for quote in quotes], total=total)


@router.post("/quotes", response_model=CrmQuoteDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    payload: CrmQuoteCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmQuoteDetailResponse:
    customer: CrmCustomer | None = None
    if payload.customer_id is not None:
        customer = await _load_customer(db, current_user.id, payload.customer_id)
    elif payload.new_customer is not None:
        customer = CrmCustomer(
            user_id=current_user.id,
            **payload.new_customer.model_dump(mode="json"),
        )
        db.add(customer)
        await db.flush()

    number = payload.number.strip() if payload.number else f"pending-{uuid_mod.uuid4()}"
    if payload.number:
        duplicate = await db.scalar(
            select(CrmQuote.id).where(CrmQuote.user_id == current_user.id, CrmQuote.number == number)
        )
        if duplicate is not None:
            raise_error(status.HTTP_409_CONFLICT, ERR_CRM_QUOTE_NUMBER_EXISTS)

    quote = CrmQuote(
        user_id=current_user.id,
        customer_id=customer.id if customer else None,
        number=number,
        title=payload.title.strip(),
        currency=payload.currency,
        valid_until=payload.valid_until,
    )
    db.add(quote)
    await db.flush()
    if not payload.number:
        profile = await db.scalar(
            select(UserCalculatorProfile).where(UserCalculatorProfile.user_id == current_user.id)
        )
        prefix = (profile.quote_number_prefix if profile else "КП").strip() or "КП"
        quote.number = f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{quote.id:05d}"

    version_payload = payload.model_copy(
        update={
            "customer_snapshot": payload.customer_snapshot or _customer_snapshot(customer),
            "html_content": payload.html_content.replace("{{CRM_QUOTE_NUMBER}}", quote.number)
            if payload.html_content
            else None,
        }
    )
    await _add_version(db, quote, version_payload, 1, current_user.id)
    db.add(
        CrmQuoteEvent(
            quote_id=quote.id,
            actor_user_id=current_user.id,
            event_type=CrmQuoteEventType.CREATED,
            details={"number": quote.number},
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise_error(status.HTTP_409_CONFLICT, ERR_CRM_QUOTE_NUMBER_EXISTS)
    return _serialize_quote_detail(await _load_quote(db, current_user.id, quote.id))


@router.get("/quotes/{quote_id}", response_model=CrmQuoteDetailResponse)
async def get_quote(
    quote_id: int,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmQuoteDetailResponse:
    return _serialize_quote_detail(await _load_quote(db, current_user.id, quote_id))


@router.patch("/quotes/{quote_id}", response_model=CrmQuoteDetailResponse)
async def update_quote(
    quote_id: int,
    payload: CrmQuoteUpdate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmQuoteDetailResponse:
    quote = await _load_quote(db, current_user.id, quote_id)
    changes = payload.model_dump(exclude_unset=True)
    if "customer_id" in changes:
        customer_id = changes.pop("customer_id")
        customer = await _load_customer(db, current_user.id, customer_id) if customer_id is not None else None
        if quote.customer_id != customer_id:
            db.add(
                CrmQuoteEvent(
                    quote_id=quote.id,
                    actor_user_id=current_user.id,
                    event_type=CrmQuoteEventType.CUSTOMER_CHANGED,
                    details={"customer_id": customer_id},
                )
            )
        quote.customer = customer
    for field_name, value in changes.items():
        setattr(quote, field_name, value.strip() if isinstance(value, str) else value)
    await db.commit()
    return _serialize_quote_detail(await _load_quote(db, current_user.id, quote.id))


@router.post("/quotes/{quote_id}/versions", response_model=CrmQuoteDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_quote_version(
    quote_id: int,
    payload: CrmQuoteVersionCreate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmQuoteDetailResponse:
    quote = await _load_quote(db, current_user.id, quote_id)
    if quote.status == CrmQuoteStatus.ACCEPTED:
        raise_error(status.HTTP_409_CONFLICT, ERR_CRM_QUOTE_LOCKED)
    previous_status = quote.status
    await _add_version(db, quote, payload, _current_version(quote).version_number + 1, current_user.id)
    if previous_status != CrmQuoteStatus.DRAFT:
        quote.status = CrmQuoteStatus.DRAFT
        db.add(
            CrmQuoteEvent(
                quote_id=quote.id,
                actor_user_id=current_user.id,
                event_type=CrmQuoteEventType.STATUS_CHANGED,
                from_status=previous_status.value,
                to_status=CrmQuoteStatus.DRAFT.value,
                details={"reason": "new_version"},
            )
        )
    await db.commit()
    return _serialize_quote_detail(await _load_quote(db, current_user.id, quote.id))


@router.post("/quotes/{quote_id}/status", response_model=CrmQuoteDetailResponse)
async def update_quote_status(
    quote_id: int,
    payload: CrmQuoteStatusUpdate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmQuoteDetailResponse:
    quote = await _load_quote(db, current_user.id, quote_id)
    previous = quote.status
    target = payload.status
    if target == previous:
        return _serialize_quote_detail(quote)
    if target not in QUOTE_STATUS_TRANSITIONS[previous]:
        raise_error(
            status.HTTP_409_CONFLICT,
            ERR_CRM_INVALID_STATUS_TRANSITION,
            {"from_status": previous.value, "to_status": target.value},
        )

    now = datetime.now(timezone.utc)
    quote.status = target
    if target == CrmQuoteStatus.SENT:
        quote.sent_at = now
    elif target == CrmQuoteStatus.ACCEPTED:
        quote.accepted_at = now
    elif target == CrmQuoteStatus.REJECTED:
        quote.rejected_at = now
    db.add(
        CrmQuoteEvent(
            quote_id=quote.id,
            actor_user_id=current_user.id,
            event_type=CrmQuoteEventType.STATUS_CHANGED,
            from_status=previous.value,
            to_status=target.value,
        )
    )

    if target == CrmQuoteStatus.ACCEPTED and quote.order is None:
        current = _current_version(quote)
        order = CrmOrder(
            user_id=current_user.id,
            quote_id=quote.id,
            customer_id=quote.customer_id,
            number=f"pending-{uuid_mod.uuid4()}",
            title=quote.title,
            currency=quote.currency,
            total=current.grand_total,
        )
        db.add(order)
        await db.flush()
        order.number = f"ЗК-{now:%Y%m%d}-{order.id:05d}"

    await db.commit()
    return _serialize_quote_detail(await _load_quote(db, current_user.id, quote.id))


@router.post("/quotes/{quote_id}/share", response_model=CrmShareQuoteResponse)
async def share_quote(
    quote_id: int,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmShareQuoteResponse:
    quote = await _load_quote(db, current_user.id, quote_id)
    version = _current_version(quote)
    if not version.html_content:
        raise_error(status.HTTP_409_CONFLICT, ERR_CRM_QUOTE_HAS_NO_DOCUMENT)
    existing = await db.get(SharedQuote, version.shared_quote_id) if version.shared_quote_id else None
    now = datetime.now(timezone.utc)
    if existing is None or (existing.expires_at is not None and existing.expires_at < now):
        existing = SharedQuote(
            user_id=current_user.id,
            title=quote.number,
            html_content=version.html_content,
            expires_at=now + timedelta(days=SHARED_QUOTE_LIFETIME_DAYS),
        )
        db.add(existing)
        await db.flush()
        version.shared_quote_id = existing.id
    db.add(
        CrmQuoteEvent(
            quote_id=quote.id,
            actor_user_id=current_user.id,
            event_type=CrmQuoteEventType.SHARED,
            details={"version_number": version.version_number},
        )
    )
    await db.commit()
    return CrmShareQuoteResponse(
        uuid=existing.uuid,
        share_url=f"{settings.BASE_URL}/quote/{existing.uuid}",
        expires_at=existing.expires_at,
    )


@router.get("/orders", response_model=CrmOrderListResponse)
async def list_orders(
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: CrmOrderStatus | None = Query(None, alias="status"),
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
) -> CrmOrderListResponse:
    filters = [CrmOrder.user_id == current_user.id]
    if status_filter is not None:
        filters.append(CrmOrder.status == status_filter)
    query = select(CrmOrder).outerjoin(CrmCustomer).where(*filters)
    count_query = select(func.count(CrmOrder.id)).outerjoin(CrmCustomer).where(*filters)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        search_filter = or_(
            CrmOrder.number.ilike(pattern),
            CrmOrder.title.ilike(pattern),
            CrmCustomer.name.ilike(pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)
    total = await db.scalar(count_query) or 0
    orders = (
        await db.execute(
            query.options(selectinload(CrmOrder.customer))
            .order_by(CrmOrder.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).scalars().unique().all()
    return CrmOrderListResponse(items=[_serialize_order(order) for order in orders if order], total=total)


@router.patch("/orders/{order_id}", response_model=CrmOrderResponse)
async def update_order(
    order_id: int,
    payload: CrmOrderUpdate,
    current_user: Annotated[User, Depends(require_calculator_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CrmOrderResponse:
    order = await _load_order(db, current_user.id, order_id)
    changes = payload.model_dump(exclude_unset=True)
    target = changes.pop("status", None)
    if target is not None and target != order.status:
        if target not in ORDER_STATUS_TRANSITIONS[order.status]:
            raise_error(
                status.HTTP_409_CONFLICT,
                ERR_CRM_INVALID_STATUS_TRANSITION,
                {"from_status": order.status.value, "to_status": target.value},
            )
        order.status = target
        order.completed_at = datetime.now(timezone.utc) if target == CrmOrderStatus.COMPLETED else None
    for field_name, value in changes.items():
        setattr(order, field_name, value)
    await db.commit()
    return _serialize_order(await _load_order(db, current_user.id, order.id))
